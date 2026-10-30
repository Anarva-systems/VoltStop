"""Firebase Cloud Messaging dispatch for queued notifications.

The queue itself is written by a Postgres trigger; this module only drains it. With no
FCM project or service account configured the dispatcher claims nothing and reports
itself disabled, so local runs and tests never touch the network.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx
import jwt

FCM_TOKEN_URI = "https://oauth2.googleapis.com/token"
FCM_SEND_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_ANDROID_CHANNEL = "voltstop_updates"
MAX_PUSH_ATTEMPTS = 6
PUSH_BACKOFF_SECONDS = 30


class PushConfigurationError(ValueError):
    """The configured FCM credentials cannot be used."""


@dataclass(frozen=True)
class ServiceAccount:
    project_id: str
    client_email: str
    private_key: str

    @property
    def send_endpoint(self) -> str:
        return f"https://fcm.googleapis.com/v1/projects/{self.project_id}/messages:send"


def parse_service_account(raw: str, *, fallback_project_id: str = "") -> ServiceAccount:
    try:
        document = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise PushConfigurationError("FCM service account is not valid JSON") from exc
    if not isinstance(document, dict):
        raise PushConfigurationError("FCM service account must be a JSON object")
    private_key = document.get("private_key")
    client_email = document.get("client_email")
    project_id = document.get("project_id") or fallback_project_id
    if not isinstance(private_key, str) or "PRIVATE KEY" not in private_key:
        raise PushConfigurationError("FCM service account is missing a private key")
    if not isinstance(client_email, str) or "@" not in client_email:
        raise PushConfigurationError("FCM service account is missing a client email")
    if not project_id:
        raise PushConfigurationError("FCM project id could not be resolved")
    return ServiceAccount(project_id=str(project_id), client_email=client_email, private_key=private_key)


def signed_assertion(account: ServiceAccount, *, now: int | None = None) -> str:
    issued = int(time.time() if now is None else now)
    claims = {
        "iss": account.client_email,
        "scope": FCM_SEND_SCOPE,
        "aud": FCM_TOKEN_URI,
        "iat": issued,
        "exp": issued + 3600,
    }
    return jwt.encode(claims, account.private_key, algorithm="RS256")


class PushSender(Protocol):
    async def send(self, *, token: str, title: str, body: str, data: dict[str, str]) -> None: ...


class PermanentPushFailure(RuntimeError):
    """The provider will never accept this device token; stop queueing for it."""


class RetryablePushFailure(RuntimeError):
    """The provider asked us to try this delivery again later."""


class FcmSender:
    """Minimal FCM HTTP v1 client on top of an injected OAuth token supplier."""

    def __init__(self, http_client: httpx.AsyncClient, account: ServiceAccount,
                 access_token: Any) -> None:
        self._http = http_client
        self._account = account
        self._access_token = access_token

    async def send(self, *, token: str, title: str, body: str, data: dict[str, str]) -> None:
        assertion = await self._access_token()
        payload = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body, "silent": False},
                "data": data,
                "android": {"notification": {"channel_id": FCM_ANDROID_CHANNEL}},
            }
        }
        response = await self._http.post(
            self._account.send_endpoint,
            json=payload,
            headers={"authorization": f"Bearer {assertion}"},
            timeout=httpx.Timeout(6.0),
        )
        if response.status_code == 200:
            return
        reason = _error_reason(response.text)
        if response.status_code in (400, 403, 404) or reason in (
            "UNREGISTERED", "SENDER_ID_MISMATCH", "INVALID_ARGUMENT"
        ):
            raise PermanentPushFailure(reason or f"HTTP {response.status_code}")
        raise RetryablePushFailure(reason or f"HTTP {response.status_code}")


def _error_reason(body: str) -> str:
    try:
        document = json.loads(body)
    except (TypeError, ValueError):
        return ""
    details = document.get("error", {}).get("details") if isinstance(document, dict) else None
    if isinstance(details, list):
        for detail in details:
            if isinstance(detail, dict) and isinstance(detail.get("reason"), str):
                return detail["reason"]
    return ""


class CachedAccessToken:
    """Mints and reuses the OAuth access token until sixty seconds before expiry."""

    def __init__(self, http_client: httpx.AsyncClient, account: ServiceAccount,
                 clock: Any = time.time) -> None:
        self._http = http_client
        self._account = account
        self._clock = clock
        self._token = ""
        self._expires_at = 0.0

    async def __call__(self) -> str:
        now = float(self._clock())
        if self._token and now < self._expires_at - 60:
            return self._token
        response = await self._http.post(
            FCM_TOKEN_URI,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_assertion(self._account, now=int(now)),
            },
            timeout=httpx.Timeout(6.0),
        )
        response.raise_for_status()
        document = response.json()
        access_token = document.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise RetryablePushFailure("FCM oauth token missing")
        lifetime = document.get("expires_in")
        self._token = access_token
        self._expires_at = now + (int(lifetime) if isinstance(lifetime, int) else 3600)
        return access_token


@dataclass(frozen=True)
class PushOutcome:
    claimed: int = 0
    sent: int = 0
    skipped: int = 0
    retried: int = 0
    disabled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"claimed": self.claimed, "sent": self.sent, "skipped": self.skipped,
                "retried": self.retried, "disabled": self.disabled}


class PushDispatcher:
    def __init__(self, pool: Any, sender: PushSender | None) -> None:
        self.pool = pool
        self.sender = sender

    async def dispatch(self, *, user_id: UUID | None = None, limit: int = 10) -> dict[str, Any]:
        if self.sender is None:
            return PushOutcome(disabled=True).as_dict()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select d.id, d.attempt_count, n.id as notification_id, n.user_id,
                          n.title, n.message, n.type, n.booking_id, device.token
                   from public.push_deliveries d
                   join public.notifications n on n.id = d.notification_id
                   left join lateral (
                     select t.token
                     from public.user_push_tokens t
                     where t.user_id = n.user_id and t.provider = 'fcm'
                     order by t.last_seen_at desc
                     limit 1
                   ) device on true
                   where d.status in ('pending', 'failed')
                     and d.available_at <= now()
                     and ($1::uuid is null or n.user_id = $1::uuid)
                   order by d.available_at
                   limit $2
                   for update of d skip locked""",
                user_id, limit,
            )
            if rows:
                # Claim before the network calls so a second drain cannot pick the same rows up.
                await conn.execute(
                    """update public.push_deliveries
                       set status = 'sending', updated_at = now()
                       where id = any($1::uuid[])""",
                    [row["id"] for row in rows],
                )
        sent = skipped = retried = 0
        for row in rows:
            attempts = int(row["attempt_count"]) + 1
            if row["token"] is None:
                await self._finish(row["id"], attempts, status="skipped",
                                   reason="no_registered_device", delivered=False)
                skipped += 1
                continue
            try:
                await self.sender.send(
                    token=row["token"],
                    title=row["title"],
                    body=row["message"],
                    data={
                        "notification_id": str(row["notification_id"]),
                        "type": row["type"],
                        "booking_id": str(row["booking_id"]) if row["booking_id"] else "",
                    },
                )
            except PermanentPushFailure as failure:
                await self._finish(row["id"], attempts, status="skipped",
                                   reason=str(failure)[:200], delivered=True)
                skipped += 1
            except (RetryablePushFailure, httpx.HTTPError) as failure:
                if attempts >= MAX_PUSH_ATTEMPTS:
                    await self._finish(row["id"], attempts, status="skipped",
                                       reason=f"attempts exhausted: {str(failure)[:160]}",
                                       delivered=False)
                    skipped += 1
                else:
                    await self._retry(row["id"], attempts, str(failure)[:200])
                    retried += 1
            else:
                await self._finish(row["id"], attempts, status="sent", reason=None, delivered=True)
                sent += 1
        return PushOutcome(claimed=len(rows), sent=sent, skipped=skipped, retried=retried).as_dict()

    async def _finish(self, delivery_id: UUID, attempts: int, *, status: str,
                      reason: str | None, delivered: bool) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """update public.push_deliveries
                   set status = $2, attempt_count = $3, last_error = $4,
                       delivered_at = case when $5 then now() else delivered_at end,
                       updated_at = now()
                   where id = $1""",
                delivery_id, status, attempts, reason, delivered,
            )

    async def _retry(self, delivery_id: UUID, attempts: int, reason: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """update public.push_deliveries
                   set status = 'failed', attempt_count = $2, last_error = $3,
                       available_at = now() + ($4 * interval '1 second'), updated_at = now()
                   where id = $1""",
                delivery_id, attempts, reason, PUSH_BACKOFF_SECONDS * attempts,
            )


def build_sender(http_client: httpx.AsyncClient, *, project_id: str,
                 service_account_json: str) -> FcmSender | None:
    if not service_account_json.strip():
        return None
    account = parse_service_account(service_account_json, fallback_project_id=project_id)
    token_source = CachedAccessToken(http_client, account)
    return FcmSender(http_client, account, token_source)
