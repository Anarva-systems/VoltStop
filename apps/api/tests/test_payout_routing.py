import hashlib
import hmac
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database_dependency import get_database
from app.core.errors import ApiError
from app.main import app
from app.payments.service import RazorpayGateway
from app.payouts.repository import PayoutRepository
from app.payouts.service import (
    MINIMUM_PLATFORM_RETENTION_BPS,
    payout_status_view,
    plan_payout,
    unroutable_reason,
)

WEBHOOK_SECRET = "payout-webhook-secret-with-at-least-32-characters"


def _vendor(**changes):
    profile = {
        "payouts_enabled": True,
        "razorpay_linked_account_id": "acc_1a2b3c4d",
        "commission_rate_bps_override": None,
        "kyc_status": "verified",
        "onboarding_status": "approved",
    }
    profile.update(changes)
    return profile


def _plan(*, gross="350.00", platform_rate=500, vendor=None, payout_id=None):
    return plan_payout(
        payout_id=payout_id or uuid4(),
        vendor=_vendor() if vendor is None else vendor,
        vendor_id=uuid4(),
        source_kind="charging_booking",
        source_reference_id=uuid4(),
        gross_amount_inr=Decimal(gross),
        platform_rate_bps=platform_rate,
    )


def test_split_is_exact_to_the_paise_and_carries_the_payout_reference():
    split = _plan()
    assert split.rate_bps == 500
    assert split.vendor_amount_inr == Decimal("332.50")
    assert split.commission_inr == Decimal("17.50")
    assert split.vendor_amount_paise + int(split.commission_inr * 100) == 35000

    transfer = split.transfer()
    assert transfer == {
        "account_id": "acc_1a2b3c4d",
        "amount": 33250,
        "currency": "INR",
        "notes": {"voltstop_payout_id": split.payout_id},
        "options": {"utr": True},
    }


def test_vendor_share_and_commission_never_exceed_the_collected_amount():
    for gross in ("1.00", "99.99", "350.00", "12345.67"):
        split = _plan(gross=gross)
        assert split.vendor_amount_inr + split.commission_inr == split.gross_amount_inr
        assert split.vendor_amount_inr > 0 and split.commission_inr > 0


@pytest.mark.parametrize(
    "profile,reason",
    [
        (None, "vendor_profile_missing"),
        (_vendor(payouts_enabled=False), "payouts_disabled"),
        (_vendor(razorpay_linked_account_id=None), "linked_account_missing"),
        (_vendor(razorpay_linked_account_id="acc_1a2b3c4d;drop"), "linked_account_missing"),
        (_vendor(kyc_status="under_review"), "kyc_not_verified"),
        (_vendor(onboarding_status="pending"), "onboarding_not_approved"),
        (_vendor(commission_rate_bps_override=6000), "commission_rate_invalid"),
    ],
)
def test_routing_is_refused_until_the_destination_is_trusted(profile, reason):
    assert unroutable_reason(profile) == reason
    if profile is not None:
        assert _plan(vendor=profile) is None


def test_payout_status_view_names_the_step_a_vendor_is_missing():
    view = payout_status_view(
        _vendor(kyc_status="submitted", platform_rate_bps=500, routed_inr=Decimal("0.00")),
        settlement_enabled=True,
    )
    assert view["state"] == "kyc_required"
    assert view["blocked_reason"] == "kyc_not_verified"
    assert view["commission_rate_bps"] == 500
    assert view["commission_rate_source"] == "platform_policy"
    assert view["kyc"]["status"] == "submitted"


def test_payout_status_view_honours_the_override_and_the_platform_policy_gate():
    profile = _vendor(commission_rate_bps_override=400, platform_rate_bps=500)
    routed = payout_status_view(profile, settlement_enabled=True)
    assert routed["state"] == "routing_enabled"
    assert routed["linked_account_id"] == "acc_1a2b3c4d"
    gated = payout_status_view(profile, settlement_enabled=False)
    assert gated["state"] == "ready_disabled"
    assert gated["blocked_reason"] is None
    assert gated["commission_rate_bps"] == 400
    assert gated["commission_rate_source"] == "vendor_override"


def test_a_rate_thinner_than_the_provider_fee_is_not_routed():
    assert MINIMUM_PLATFORM_RETENTION_BPS == 300
    assert _plan(platform_rate=100) is None
    assert _plan(vendor=_vendor(commission_rate_bps_override=200)) is None
    assert unroutable_reason(_vendor(commission_rate_bps_override=200)) == "platform_retention_below_floor"
    assert unroutable_reason(_vendor(commission_rate_bps_override=MINIMUM_PLATFORM_RETENTION_BPS)) is None
    assert _plan(platform_rate=300).rate_bps == 300


class _LedgerConnection:
    """In-memory stand-in for public.vendor_payout_transfers."""

    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.inserts = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "insert into public.vendor_payout_transfers" in normalized:
            self.inserts.append(args)
            if any(row["razorpay_order_id"] == args[4] and row["vendor_id"] == args[1]
                   for row in self.rows.values()):
                return None  # on conflict (razorpay_order_id, vendor_id) do nothing
            self.rows[args[0]] = {
                "id": args[0], "vendor_id": args[1], "status": "planned",
                "razorpay_transfer_id": None, "razorpay_payment_id": None,
                "currency": "INR", "vendor_amount_inr": args[6],
                "gross_amount_inr": args[5], "rate_bps": args[8],
                "razorpay_order_id": args[4],
                "settlement_utr": None, "failure_reason": None, "provider_event_at": None,
            }
            return {"id": args[0]}
        if "from public.vendor_payout_transfers where id = $1 for update" in normalized:
            row = self.rows.get(args[0])
            return dict(row) if row else None
        if "update public.vendor_payout_transfers" in normalized:
            row = self.rows[args[0]]
            row.update(status=args[1], razorpay_transfer_id=args[2],
                       razorpay_payment_id=args[3])
            return dict(row)
        raise AssertionError(f"Unexpected fetchrow query: {normalized}")


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _Acquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _Acquire(self.connection)


def _run(coroutine):
    import asyncio

    return asyncio.run(coroutine)


def test_ledger_row_records_the_split_that_travelled_with_the_order():
    split = _plan()
    connection = _LedgerConnection()

    async def run():
        return await PayoutRepository(_Pool(connection)).record_planned_transfer(
            split, "order_double_1")

    assert _run(run()) is True
    args = connection.inserts[0]
    assert args[4] == "order_double_1"
    assert args[5] == split.gross_amount_inr
    assert args[6] == split.vendor_amount_inr
    assert args[7] == split.commission_inr
    assert connection.rows[UUID(split.payout_id)]["status"] == "planned"

    async def replay():
        return await PayoutRepository(_Pool(_LedgerConnection(connection.rows))).record_planned_transfer(
            split, "order_double_1")

    assert _run(replay()) is False


def test_transfer_events_walk_the_ledger_state_machine():
    split = _plan()
    connection = _LedgerConnection()
    _run(PayoutRepository(_Pool(connection)).record_planned_transfer(split, "order_double_1"))
    payout_id = UUID(split.payout_id)

    async def event(name):
        return await PayoutRepository(_Pool(connection)).apply_transfer_event(
            payout_id=payout_id, event=name, transfer_id="trf_double_1",
            source_payment_id="pay_double_1", amount_paise=33250, currency="INR")

    assert _run(event("transfer.processed"))["status"] == "processed"
    assert _run(event("transfer.processed"))["status"] == "processed"
    settled = _run(event("transfer.settled"))
    assert settled["status"] == "settled"
    assert settled["razorpay_transfer_id"] == "trf_double_1"

    with pytest.raises(ApiError) as conflict:
        _run(event("transfer.processed"))
    assert conflict.value.status_code == 409
    assert conflict.value.detail["code"] == "PAYOUT_STATE_CONFLICT"


def test_amount_mismatch_is_refused_before_the_ledger_moves():
    split = _plan()
    connection = _LedgerConnection()
    _run(PayoutRepository(_Pool(connection)).record_planned_transfer(split, "order_double_1"))

    async def run():
        return await PayoutRepository(_Pool(connection)).apply_transfer_event(
            payout_id=UUID(split.payout_id), event="transfer.processed",
            transfer_id="trf_double_1", source_payment_id="pay_double_1",
            amount_paise=35000, currency="INR")

    with pytest.raises(ApiError) as error:
        _run(run())
    assert error.value.detail["code"] == "PAYOUT_AMOUNT_MISMATCH"
    assert connection.rows[UUID(split.payout_id)]["status"] == "planned"


class _RecordingClient:
    def __init__(self, response):
        self.calls = []
        self.response = response

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class _OrderResponse:
    is_error = False

    def json(self):
        return {"id": "order_double_1", "amount": 35000, "currency": "INR"}


def _gateway(client):
    return RazorpayGateway(client, SimpleNamespace(
        razorpay_key_id="rzp_test_double", razorpay_key_secret="secret", razorpay_mode="test"))


def test_order_payload_carries_the_transfer_instruction():
    split = _plan()
    client = _RecordingClient(_OrderResponse())

    order = _run(_gateway(client).create_order(uuid4(), Decimal("350.00"), [split.transfer()]))

    assert order["order_id"] == "order_double_1"
    _, kwargs = client.calls[0]
    assert kwargs["json"]["amount"] == 35000
    assert kwargs["json"]["transfers"] == [split.transfer()]


def test_a_transfer_that_eats_the_whole_order_is_refused_without_calling_the_provider():
    client = _RecordingClient(_OrderResponse())
    with pytest.raises(ApiError) as error:
        _run(_gateway(client).create_order(
            uuid4(), Decimal("350.00"),
            [{"account_id": "acc_1a2b3c4d", "amount": 35000, "currency": "INR"}]))

    assert error.value.status_code == 503
    assert error.value.detail["code"] == "PAYOUT_PLAN_INVALID"
    assert client.calls == []


def test_a_malformed_destination_is_refused_without_calling_the_provider():
    client = _RecordingClient(_OrderResponse())
    with pytest.raises(ApiError) as error:
        _run(_gateway(client).create_order(
            uuid4(), Decimal("350.00"),
            [{"account_id": "acc_1a2b3c4d;drop", "amount": 1000, "currency": "INR"}]))

    assert error.value.detail["code"] == "PAYOUT_PLAN_INVALID"
    assert client.calls == []


def test_payout_routing_migration_is_additive_and_masks_kyc():
    from pathlib import Path

    migration = (Path(__file__).resolve().parents[3]
                 / "supabase/migrations/202610290003_vendor_payout_routing.sql").read_text(
                     encoding="utf-8").lower()
    assert "razorpay_linked_account_id text check" in migration
    assert "razorpay_linked_account_id ~ '^acc_" in migration
    assert "payouts_enabled boolean not null default false" in migration
    assert "commission_rate_bps_override smallint check" in migration
    assert "between 0 and 5000" in migration
    assert "kyc_pan_masked text check" in migration
    assert "bank_account_masked text check" in migration
    assert "constraint vendor_payout_split_is_exhaustive check" in migration
    assert "constraint vendor_payout_source_unique unique (razorpay_order_id, vendor_id)" in migration
    assert "enable row level security" in migration
    assert "revoke all on public.vendor_payout_transfers from anon" in migration
    for destructive in ("drop table", "delete from", "truncate", "drop column"):
        assert destructive not in migration


@contextmanager
def _webhook_client(connection):
    class _Database:
        def __init__(self, pool):
            self.pool = pool

    async def fake_database():
        return _Database(_Pool(connection))

    settings = get_settings()
    old = (settings.razorpay_webhook_secret, settings.database_url, settings.redis_enabled)
    app.dependency_overrides[get_database] = fake_database
    settings.razorpay_webhook_secret = WEBHOOK_SECRET
    settings.database_url = ""
    settings.redis_enabled = False
    try:
        with TestClient(app) as client:
            yield client
    finally:
        (settings.razorpay_webhook_secret, settings.database_url,
         settings.redis_enabled) = old
        app.dependency_overrides.clear()


def _post_transfer(client, payout_id, event, amount_paise, transfer_id="trf_double_1"):
    body = json.dumps({
        "event": event,
        "occurred_at": int(datetime.now(timezone.utc).timestamp()),
        "payload": {"transfer": {"entity": {
            "id": transfer_id, "entity": "transfer", "source": "pay_double_1",
            "amount": amount_paise, "currency": "INR", "status": "processed",
            "notes": {"voltstop_payout_id": str(payout_id)}}}},
    }).encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/api/v1/payments/razorpay/webhook", content=body,
                       headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"})


def test_transfer_webhook_moves_the_ledger_row():
    split = _plan()
    connection = _LedgerConnection()
    _run(PayoutRepository(_Pool(connection)).record_planned_transfer(split, "order_double_1"))
    payout_id = UUID(split.payout_id)

    with _webhook_client(connection) as client:
        processed = _post_transfer(client, payout_id, "transfer.processed", 33250)
        assert processed.status_code == 200
        assert processed.json()["data"]["status"] == "processed"

        replay = _post_transfer(client, payout_id, "transfer.processed", 33250)
        assert replay.status_code == 200

        mismatch = _post_transfer(client, payout_id, "transfer.settled", 35000)
        assert mismatch.status_code == 409
        assert mismatch.json()["error"]["code"] == "PAYOUT_AMOUNT_MISMATCH"

    assert connection.rows[payout_id]["status"] == "processed"


def test_transfer_webhook_without_a_ledger_row_is_reported_as_missing():
    with _webhook_client(_LedgerConnection()) as client:
        response = _post_transfer(client, uuid4(), "transfer.processed", 33250)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAYOUT_NOT_FOUND"
