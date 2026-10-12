import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.database import Database
from app.core.errors import ApiError


class FakeTransaction:
    def __init__(self, lock):
        self.lock = lock

    async def __aenter__(self):
        await self.lock.acquire()

    async def __aexit__(self, exc_type, exc, traceback):
        self.lock.release()


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class FakePaymentConnection:
    """Small transactional SQL double for exercising the repository method."""

    def __init__(self):
        self.payment_id = uuid4()
        self.booking_id = uuid4()
        self.slot_id = uuid4()
        self.order_id = "order_test_123"
        self.payment = {
            "payment_id": self.payment_id,
            "booking_id": self.booking_id,
            "razorpay_order_id": self.order_id,
            "amount_inr": Decimal("350.00"),
            "currency": "INR",
            "payment_status": "pending",
            "razorpay_payment_id": None,
        }
        self.refund_id = uuid4()
        self.refund = {
            "id": self.refund_id,
            "requested_by": uuid4(),
            "payment_id": self.payment_id,
            "amount_inr": Decimal("350.00"),
            "status": "requested",
            "dispute_id": uuid4(),
            "razorpay_refund_id": None,
        }
        self.booking = {
            "id": self.booking_id,
            "payment_id": self.payment_id,
            "booking_status": "pending",
            "slot_id": self.slot_id,
        }
        self.booking_events = []
        self.refund_events = []
        self.refund_audit_events = []
        self.duplicate_provider_payment_id = None
        self.lock = asyncio.Lock()

    def transaction(self):
        return FakeTransaction(self.lock)

    async def fetchrow(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.payments where razorpay_order_id=$1" in normalized:
            if args[0] != self.order_id:
                return None
            return {"payment_id": self.payment_id, "booking_id": self.payment["booking_id"]}
        if "from public.bookings where id=$1 and payment_id=$2 for update" in normalized:
            if args[0] != self.booking_id or args[1] != self.booking["payment_id"]:
                return None
            return dict(self.booking)
        if "from public.payments where id=$1 for update" in normalized:
            if args[0] != self.payment_id:
                return None
            return dict(self.payment)
        if "where razorpay_payment_id=$1 and id<>$2" in normalized:
            if args[0] == self.duplicate_provider_payment_id:
                return {"id": uuid4()}
            return None
        if "from public.refunds r join public.payments p" in normalized:
            refund_id, payment_id, local_id = args
            matches_provider_id = self.refund["razorpay_refund_id"] == refund_id
            matches_local_id = local_id is not None and str(self.refund_id) == local_id
            if payment_id != "pay_correct" or not (matches_provider_id or matches_local_id):
                return None
            return {
                **self.refund,
                "currency": "INR",
                "payment_status": self.payment["payment_status"],
            }
        raise AssertionError(f"Unexpected fetchrow query: {normalized}")

    async def fetchval(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "sum(amount_inr)" in normalized and "from public.refunds" in normalized:
            return sum((self.refund["amount_inr"] for _ in [0]
                        if self.refund["payment_id"] == args[0] and self.refund["status"] == "completed"),
                       Decimal("0.00"))
        if "select amount_inr from public.payments" in normalized:
            return self.payment["amount_inr"]
        raise AssertionError(f"Unexpected fetchval query: {normalized}")

    async def execute(self, query, *args):
        normalized = " ".join(query.lower().split())
        if normalized.startswith("update public.payments set status="):
            if len(args) == 1:
                self.payment["payment_status"] = "refunded"
            else:
                self.payment["payment_status"] = args[1]
                self.payment["razorpay_payment_id"] = args[2]
            return "UPDATE 1"
        if normalized.startswith("insert into public.booking_events"):
            event_type = args[1] if len(args) > 1 else normalized.split("values ($1, '", 1)[1].split("'", 1)[0]
            self.booking_events.append((args[0], event_type))
            return "INSERT 0 1"
        if normalized.startswith("update public.refunds set razorpay_refund_id="):
            self.refund["razorpay_refund_id"] = self.refund["razorpay_refund_id"] or args[1]
            self.refund["status"] = args[2]
            return "UPDATE 1"
        if normalized.startswith("insert into public.admin_audit_logs"):
            self.refund_audit_events.append(tuple(args))
            return "INSERT 0 1"
        if normalized.startswith("insert into public.dispute_events"):
            self.refund_events.append(tuple(args))
            return "INSERT 0 1"
        if normalized.startswith("update public.payments set status='refunded'"):
            self.payment["payment_status"] = "refunded"
            return "UPDATE 1"
        if normalized.startswith("update public.bookings set status='confirmed'"):
            self.booking["booking_status"] = "confirmed"
            return "UPDATE 1"
        if normalized.startswith("update public.bookings set status='expired'"):
            self.booking["booking_status"] = "expired"
            return "UPDATE 1"
        if normalized.startswith("update public.charging_slots"):
            return "UPDATE 0"
        raise AssertionError(f"Unexpected execute query: {normalized}")


class FakePaymentPool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return FakeAcquire(self.connection)


def make_database():
    connection = FakePaymentConnection()
    return Database(FakePaymentPool(connection)), connection


def run_webhook(database, order_id, payment_id, amount=35000, currency="INR", captured=True):
    return asyncio.run(database.process_payment_webhook(
        order_id, payment_id, amount, currency, captured
    ))


def run_refund_webhook(database, refund_id, payment_id="pay_correct", amount=35000,
                       currency="INR", provider_status="processed", local_id=None):
    return asyncio.run(database.process_refund_webhook(
        refund_id, payment_id, amount, currency, provider_status, local_id
    ))


def snapshot(connection):
    return (
        dict(connection.payment),
        dict(connection.booking),
        list(connection.booking_events),
    )


def test_rejects_validly_signed_webhook_with_wrong_provider_payment_id_without_mutation():
    database, connection = make_database()
    connection.payment.update(payment_status="captured", razorpay_payment_id="pay_correct")
    connection.booking["booking_status"] = "confirmed"
    before = snapshot(connection)

    with pytest.raises(ApiError) as error:
        run_webhook(database, connection.order_id, "pay_wrong")

    assert error.value.status_code == 400
    assert error.value.detail == {
        "code": "PAYMENT_WEBHOOK_REJECTED",
        "message": "Webhook payment could not be verified",
    }
    assert snapshot(connection) == before


@pytest.mark.parametrize("amount", [34999, 35001])
def test_rejects_amount_below_or_above_server_amount_without_mutation(amount):
    database, connection = make_database()
    before = snapshot(connection)

    with pytest.raises(ApiError) as error:
        run_webhook(database, connection.order_id, "pay_correct", amount=amount)

    assert error.value.detail["code"] == "PAYMENT_AMOUNT_MISMATCH"
    assert snapshot(connection) == before


def test_rejects_currency_mismatch_without_mutation():
    database, connection = make_database()
    before = snapshot(connection)

    with pytest.raises(ApiError):
        run_webhook(database, connection.order_id, "pay_correct", currency="USD")

    assert snapshot(connection) == before


def test_rejects_unknown_provider_order_without_mutation():
    database, connection = make_database()
    before = snapshot(connection)

    assert not run_webhook(database, "order_other", "pay_correct")
    assert snapshot(connection) == before


def test_rejects_booking_payment_pointer_mismatch_without_mutation():
    database, connection = make_database()
    connection.booking["payment_id"] = uuid4()
    before = snapshot(connection)

    assert not run_webhook(database, connection.order_id, "pay_correct")
    assert snapshot(connection) == before


def test_rejects_provider_payment_id_already_linked_to_another_internal_payment():
    database, connection = make_database()
    connection.duplicate_provider_payment_id = "pay_bound_elsewhere"
    before = snapshot(connection)

    with pytest.raises(ApiError) as error:
        run_webhook(database, connection.order_id, "pay_bound_elsewhere")

    assert error.value.detail["code"] == "PAYMENT_WEBHOOK_REJECTED"
    assert snapshot(connection) == before


def test_duplicate_and_triple_capture_replay_have_one_effective_transition():
    database, connection = make_database()

    assert run_webhook(database, connection.order_id, "pay_correct")
    after_first = snapshot(connection)
    assert connection.payment["payment_status"] == "captured"
    assert connection.booking["booking_status"] == "confirmed"
    assert [event for _, event in connection.booking_events] == ["payment_success", "confirmed"]

    assert run_webhook(database, connection.order_id, "pay_correct")
    assert run_webhook(database, connection.order_id, "pay_correct")
    assert snapshot(connection) == after_first


def test_concurrent_duplicate_capture_replay_has_one_effective_transition():
    database, connection = make_database()

    async def process_concurrently():
        return await asyncio.gather(*[
            database.process_payment_webhook(
                connection.order_id, "pay_correct", 35000, "INR", True
            ) for _ in range(2)
        ])

    assert asyncio.run(process_concurrently()) == [True, True]
    assert connection.payment["payment_status"] == "captured"
    assert connection.booking["booking_status"] == "confirmed"
    assert [event for _, event in connection.booking_events] == ["payment_success", "confirmed"]


def test_older_failure_after_capture_does_not_regress_final_state():
    database, connection = make_database()
    assert run_webhook(database, connection.order_id, "pay_correct")
    after_capture = snapshot(connection)

    assert run_webhook(database, connection.order_id, "pay_correct", captured=False)
    assert snapshot(connection) == after_capture


def test_late_capture_after_failure_is_recorded_without_reconfirming_expired_booking():
    database, connection = make_database()
    assert run_webhook(database, connection.order_id, "pay_correct", captured=False)
    assert connection.payment["payment_status"] == "failed"
    assert connection.booking["booking_status"] == "expired"
    after_failure = snapshot(connection)

    assert run_webhook(database, connection.order_id, "pay_correct", captured=True)
    assert connection.payment["payment_status"] == "captured"
    assert connection.booking["booking_status"] == "expired"
    assert len(connection.booking_events) == len(after_failure[2]) + 1


def test_refund_webhook_replay_does_not_duplicate_refund_audit_or_dispute_events():
    database, connection = make_database()
    connection.payment["razorpay_payment_id"] = "pay_correct"
    refund_id = "rfnd_test_123"

    assert run_refund_webhook(database, refund_id, local_id=str(connection.refund_id))
    after_first = (
        dict(connection.refund), connection.payment["payment_status"],
        len(connection.refund_audit_events), len(connection.refund_events),
    )
    assert connection.refund["status"] == "completed"
    assert connection.payment["payment_status"] == "refunded"
    assert run_refund_webhook(database, refund_id, local_id=str(connection.refund_id))

    assert after_first == (dict(connection.refund), "refunded", 1, 1)
    assert len(connection.refund_audit_events) == 1
    assert len(connection.refund_events) == 1


def test_refund_id_mismatch_via_local_reference_has_no_financial_effect():
    database, connection = make_database()
    connection.payment["razorpay_payment_id"] = "pay_correct"
    connection.refund["razorpay_refund_id"] = "rfnd_stored"
    before = (
        dict(connection.refund), connection.payment["payment_status"],
        list(connection.refund_audit_events), list(connection.refund_events),
    )

    with pytest.raises(ApiError) as error:
        run_refund_webhook(database, "rfnd_wrong", local_id=str(connection.refund_id))

    assert error.value.detail["code"] == "REFUND_WEBHOOK_REJECTED"
    assert before == (
        dict(connection.refund), connection.payment["payment_status"],
        connection.refund_audit_events, connection.refund_events,
    )
