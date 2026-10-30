import json
import time
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.notifications.push import (
    FcmSender,
    MAX_PUSH_ATTEMPTS,
    PermanentPushFailure,
    PushConfigurationError,
    PushDispatcher,
    RetryablePushFailure,
    CachedAccessToken,
    build_sender,
    parse_service_account,
    signed_assertion,
)

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()
PUBLIC_PEM = KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()
ACCOUNT_DOC = {
    "project_id": "voltstop-app",
    "client_email": "push@voltstop-app.iam.gserviceaccount.com",
    "private_key": PRIVATE_PEM,
}


class _Account:
    project_id = "voltstop-app"
    client_email = ACCOUNT_DOC["client_email"]
    private_key = PRIVATE_PEM
    send_endpoint = "https://fcm.googleapis.com/v1/projects/voltstop-app/messages:send"


def test_service_account_is_parsed_and_validated():
    account = parse_service_account(json.dumps(ACCOUNT_DOC))
    assert account.project_id == "voltstop-app"
    assert account.send_endpoint.endswith("/messages:send")
    assert parse_service_account(
        json.dumps({"client_email": "a@b.test", "private_key": PRIVATE_PEM}),
        fallback_project_id="configured-project",
    ).project_id == "configured-project"


@pytest.mark.parametrize("document,reason", [
    ("not json at all", "not valid JSON"),
    ("[]", "must be a JSON object"),
    ('{"client_email":"a@b.test"}', "missing a private key"),
    ('{"private_key":"nope"}', "missing a private key"),
    (json.dumps({"private_key": PRIVATE_PEM, "client_email": "no-email"}), "missing a client email"),
])
def test_bad_service_accounts_are_refused(document, reason):
    with pytest.raises(PushConfigurationError) as error:
        parse_service_account(document)
    assert reason in str(error.value)


def test_missing_credentials_never_build_a_sender():
    assert build_sender(httpx.AsyncClient(), project_id="", service_account_json="   ") is None


def test_signed_assertion_carries_the_fcm_scope():
    account = parse_service_account(json.dumps(ACCOUNT_DOC))
    issued = int(time.time())
    token = signed_assertion(account, now=issued)
    claims = jwt.decode(token, PUBLIC_PEM, algorithms=["RS256"],
                        options={"verify_aud": False, "verify_exp": False})
    assert claims["iss"] == ACCOUNT_DOC["client_email"]
    assert claims["scope"] == "https://www.googleapis.com/auth/firebase.messaging"
    assert claims["aud"] == "https://oauth2.googleapis.com/token"
    assert claims["iat"] == issued
    assert claims["exp"] == issued + 3600


class _Post:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def _response(status, body):
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://fcm.googleapis.com"))


def test_access_token_is_cached_until_it_expires():
    client = _Post([
        _response(200, {"access_token": "ya_first", "expires_in": 3600}),
        _response(200, {"access_token": "ya_second", "expires_in": 3600}),
    ])
    clock = {"now": 1_000.0}
    token = CachedAccessToken(client, _Account, clock=lambda: clock["now"])

    assert _run(token()) == "ya_first"
    assert _run(token()) == "ya_first"
    assert len(client.calls) == 1

    clock["now"] = 4_550.0
    assert _run(token()) == "ya_second"
    assert len(client.calls) == 2


def test_send_posts_an_fcm_v1_message_and_classifies_failures():
    client = _Post([
        _response(200, {"name": "projects/voltstop-app/messages/1"}),
        _response(404, {"error": {"details": [{"reason": "UNREGISTERED"}]}}),
        _response(429, {"error": {"details": [{"reason": "RESOURCE_EXHAUSTED"}]}}),
        _response(500, {"error": {"message": "backend trouble"}}),
    ])
    sender = FcmSender(client, _Account, _static_token("ya-token"))

    _run(sender.send(token="device-1", title="Booking confirmed", body="Seat held.",
                     data={"type": "booking_confirmed", "booking_id": "b1"}))
    url, kwargs = client.calls[0]
    assert url == "https://fcm.googleapis.com/v1/projects/voltstop-app/messages:send"
    assert kwargs["headers"]["authorization"] == "Bearer ya-token"
    message = kwargs["json"]["message"]
    assert message["token"] == "device-1"
    assert message["notification"] == {"title": "Booking confirmed", "body": "Seat held.", "silent": False}
    assert message["data"] == {"type": "booking_confirmed", "booking_id": "b1"}
    assert message["android"]["notification"]["channel_id"] == "voltstop_updates"

    with pytest.raises(PermanentPushFailure):
        _run(sender.send(token="device-1", title="t", body="b", data={}))
    with pytest.raises(RetryablePushFailure):
        _run(sender.send(token="device-1", title="t", body="b", data={}))
    with pytest.raises(RetryablePushFailure):
        _run(sender.send(token="device-1", title="t", body="b", data={}))


def _static_token(value):
    async def token():
        return value
    return token


def _run(coroutine):
    import asyncio
    return asyncio.run(coroutine)


class _Queue:
    """Stands in for the outbox table and records every state transition in order."""

    def __init__(self, rows, *, limit=None):
        self.rows = {row["id"]: dict(row) for row in rows}
        self.events = []
        self.limit = limit

    async def fetch(self, query, *args):
        assert "for update of d skip locked" in query
        self.events.append("claim")
        pending = [row for row in self.rows.values() if row["status"] in ("pending", "failed")]
        return [dict(row) for row in pending[:args[1]]]

    async def execute(self, query, *args):
        if "set status = 'sending'" in query:
            self.events.append("mark-sending")
            assert args[0]
            return "UPDATE %d" % len(args[0])
        if "status = $2" in query:
            delivery_id, status, attempts, reason, delivered = args[:5]
            self.rows[delivery_id].update({"status": status, "attempt_count": attempts,
                                           "last_error": reason,
                                           "delivered_at": "now" if delivered else None})
            self.events.append(f"{status}:{delivery_id}")
            return "UPDATE 1"
        if "status = 'failed'" in query:
            delivery_id, attempts, reason, backoff = args[:4]
            self.rows[delivery_id].update({"status": "failed", "attempt_count": attempts,
                                           "last_error": reason, "backoff_seconds": backoff})
            self.events.append(f"failed:{delivery_id}")
            return "UPDATE 1"
        raise AssertionError(f"Unexpected query: {query}")


class _Acquire:
    def __init__(self, queue):
        self.queue = queue

    async def __aenter__(self):
        return self.queue

    async def __aexit__(self, *_args):
        return None


class _Pool:
    def __init__(self, queue):
        self.queue = queue

    def acquire(self):
        return _Acquire(self.queue)


class _ExplodingPool:
    def acquire(self):
        raise AssertionError("dispatch without credentials must not touch the queue")


def _delivery(token=None, attempts=0):
    return {
        "id": uuid4(),
        "attempt_count": attempts,
        "notification_id": uuid4(),
        "user_id": uuid4(),
        "title": "Booking confirmed",
        "message": "Your booking ab12cd34 is confirmed.",
        "type": "booking_confirmed",
        "booking_id": uuid4(),
        "token": token,
        "status": "pending",
        "delivered_at": None,
        "last_error": None,
    }


class _Sender:
    def __init__(self, *failures):
        self.sent = []
        self.failures = list(failures)

    async def send(self, *, token, title, body, data):
        self.sent.append((token, title, body, data))
        if self.failures:
            raise self.failures.pop(0)


def test_dispatch_is_a_no_op_without_a_configured_sender():
    outcome = _run(PushDispatcher(_ExplodingPool(), None).dispatch())
    assert outcome == {"claimed": 0, "sent": 0, "skipped": 0, "retried": 0, "disabled": True}


def test_delivery_without_a_registered_device_is_skipped():
    row = _delivery(token=None)
    queue = _Queue([row])
    sender = _Sender()

    outcome = _run(PushDispatcher(_Pool(queue), sender).dispatch())

    assert outcome["skipped"] == 1
    assert queue.rows[row["id"]]["status"] == "skipped"
    assert queue.rows[row["id"]]["last_error"] == "no_registered_device"
    assert queue.rows[row["id"]]["delivered_at"] is None
    assert sender.sent == []


def test_rows_are_claimed_before_the_first_network_call():
    row = _delivery(token="device-1")
    queue = _Queue([row])

    _run(PushDispatcher(_Pool(queue), _Sender()).dispatch())

    assert queue.events[0] == "claim"
    assert queue.events[1] == "mark-sending"
    assert queue.events[2] == f"sent:{row['id']}"


def test_successful_send_marks_the_row_sent():
    row = _delivery(token="device-1")
    queue = _Queue([row])
    sender = _Sender()

    outcome = _run(PushDispatcher(_Pool(queue), sender).dispatch())

    assert outcome["sent"] == 1
    assert queue.rows[row["id"]]["status"] == "sent"
    assert queue.rows[row["id"]]["delivered_at"] == "now"
    assert sender.sent[0][0] == "device-1"
    assert sender.sent[0][3]["notification_id"] == str(row["notification_id"])


def test_a_dead_device_token_stops_future_attempts():
    row = _delivery(token="device-1")
    queue = _Queue([row])

    outcome = _run(PushDispatcher(_Pool(queue), _Sender(PermanentPushFailure("UNREGISTERED"))).dispatch())

    assert outcome["skipped"] == 1
    assert queue.rows[row["id"]]["status"] == "skipped"
    assert queue.rows[row["id"]]["last_error"] == "UNREGISTERED"


def test_transient_failure_is_scheduled_again_with_backoff():
    row = _delivery(token="device-1", attempts=1)
    queue = _Queue([row])

    outcome = _run(PushDispatcher(_Pool(queue), _Sender(RetryablePushFailure("RESOURCE_EXHAUSTED"))).dispatch())

    stored = queue.rows[row["id"]]
    assert outcome["retried"] == 1
    assert stored["status"] == "failed"
    assert stored["attempt_count"] == 2
    assert stored["backoff_seconds"] == 60
    assert stored["delivered_at"] is None


def test_persistent_failures_stop_after_the_attempt_budget():
    row = _delivery(token="device-1", attempts=MAX_PUSH_ATTEMPTS - 1)
    queue = _Queue([row])

    outcome = _run(PushDispatcher(_Pool(queue), _Sender(RetryablePushFailure("500"))).dispatch())

    assert outcome["skipped"] == 1
    assert queue.rows[row["id"]]["status"] == "skipped"
    assert "attempts exhausted" in queue.rows[row["id"]]["last_error"]


def test_dispatch_migration_is_additive_and_keeps_tokens_private():
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    migration = (repo_root / "supabase/migrations/202610290004_push_delivery_and_realtime.sql")\
        .read_text(encoding="utf-8").lower()
    assert "references public.profiles(id) on delete cascade" in migration
    assert "references public.users" not in migration
    assert "after insert on public.notifications" in migration
    assert "alter publication supabase_realtime add table" in migration
    assert "insert into public.push_deliveries(notification_id, user_id)" in migration
    assert "on conflict (notification_id) do nothing" in migration
    assert "security definer" in migration
    assert "revoke all on public.user_push_tokens" in migration
    for destructive in ("drop table", "delete from", "truncate", "drop column"):
        assert destructive not in migration
