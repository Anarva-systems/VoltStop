import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.database import Database
from app.core.errors import ApiError


class _Transaction:
    def __init__(self, lock):
        self.lock = lock

    async def __aenter__(self):
        await self.lock.acquire()

    async def __aexit__(self, *_):
        self.lock.release()


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_):
        return False


class _ChargingConnection:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.slot_id, self.vendor_id = uuid4(), uuid4()
        self.booking_id = uuid4()
        self.payment_id = uuid4()
        self.price = Decimal("50.00")
        self.capacity = 2
        self.bookings = {}
        self.slot_booked_updates = 0
        self.events = []
        self.expired_rows = []
        self.payment_state = {"order_state": "creating", "razorpay_order_id": None}
        self.insert_count = 0

    def transaction(self):
        return _Transaction(self.lock)

    async def fetch(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.bookings" in normalized and "hold_expires_at" in normalized:
            return list(self.expired_rows)
        raise AssertionError(f"Unexpected fetch query: {normalized}")

    async def fetchrow(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "for update of b" in normalized and "idempotency_key" in normalized:
            return self.bookings.get((args[0], args[1]))
        if "from public.charging_slots cs" in normalized and "for update of cs" in normalized:
            if args[0] != self.slot_id:
                return None
            return {"id": self.slot_id, "vendor_id": self.vendor_id, "capacity": self.capacity,
                    "price_inr": self.price, "slot_start_time": datetime.now(timezone.utc),
                    "slot_end_time": datetime.now(timezone.utc) + timedelta(hours=1),
                    "status": "available", "is_future": True, "is_active": True, "is_verified": True}
        if "insert into public.bookings" in normalized:
            self.insert_count += 1
            if self.bookings.get((args[1], args[5])) is not None:
                return None
            row = {"id": args[0], "user_id": args[1], "vendor_id": args[2], "slot_id": args[3],
                   "amount_paid": Decimal("0.00"), "status": "pending", "payment_id": self.payment_id,
                   "razorpay_order_id": None, "amount_inr": self.price, "currency": "INR",
                   "payment_status": "pending", "order_state": "creating",
                   "request_fingerprint": args[6], "idempotency_key": args[5]}
            self.bookings[(args[1], args[5])] = row
            return {"id": args[0]}
        if "where b.user_id=$1 and b.idempotency_key=$2" in normalized and "for update of b" not in normalized:
            return self.bookings.get((args[0], args[1]))
        if "where b.id=$1" in normalized:
            return next((value for value in self.bookings.values() if value["id"] == args[0]), None)
        raise AssertionError(f"Unexpected fetchrow query: {normalized}")

    async def fetchval(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "insert into public.payments" in normalized:
            return self.payment_id
        if "select count(*) from public.bookings" in normalized:
            return len([b for b in self.bookings.values() if b["status"] in ("pending", "confirmed")])
        raise AssertionError(f"Unexpected fetchval query: {normalized}")

    async def execute(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "pg_advisory_xact_lock" in normalized:
            return "SELECT 1"
        if "update public.bookings set payment_id" in normalized:
            return "UPDATE 1"
        if "update public.bookings set status='expired'" in normalized:
            for value in self.bookings.values():
                if value["id"] == args[0]:
                    value["status"] = "expired"
            return "UPDATE 1"
        if "insert into public.booking_events" in normalized:
            self.events.append(args[0])
            if "'created'" in normalized and "'payment_started'" in normalized:
                self.events.append(args[0])
            return "INSERT 0 1"
        if "update public.charging_slots" in normalized:
            self.slot_booked_updates += 1
            return "UPDATE 1"
        if "update public.payments set razorpay_order_id" in normalized:
            if args[0] != self.payment_id or self.payment_state["order_state"] != "creating":
                return "UPDATE 0"
            self.payment_state["order_state"] = "ready"
            self.payment_state["razorpay_order_id"] = args[1]
            return "UPDATE 1"
        if "update public.payments set order_state='reconciliation_required'" in normalized:
            if args[0] == self.payment_id and self.payment_state["order_state"] == "creating":
                self.payment_state["order_state"] = "reconciliation_required"
            return "UPDATE 1"
        raise AssertionError(f"Unexpected execute query: {normalized}")


class _ChargingPool:
    def __init__(self):
        self.connection = _ChargingConnection()

    def acquire(self):
        return _Acquire(self.connection)


def _values():
    pool = _ChargingPool()
    database = Database(pool)
    user = uuid4()
    return pool, database, user


def test_charging_booking_retry_with_same_key_returns_existing_booking():
    pool, database, user = _values()
    fingerprint = "fp-1"
    first, created = asyncio.run(database.create_pending_booking(
        user, pool.connection.slot_id, uuid4(), Decimal("50.00"), "lock:token-1", fingerprint, 300))
    replay, replay_created = asyncio.run(database.create_pending_booking(
        user, pool.connection.slot_id, uuid4(), Decimal("50.00"), "lock:token-1", fingerprint, 300))

    assert created is True and replay_created is False
    assert first["id"] == replay["id"]
    assert pool.connection.insert_count == 1
    assert pool.connection.events.count(first["id"]) == 2


def test_charging_booking_same_key_with_different_payload_is_rejected():
    pool, database, user = _values()
    asyncio.run(database.create_pending_booking(
        user, pool.connection.slot_id, uuid4(), Decimal("50.00"), "lock:token-1", "fp-1", 300))

    with pytest.raises(ApiError) as error:
        asyncio.run(database.create_pending_booking(
            user, pool.connection.slot_id, uuid4(), Decimal("50.00"), "lock:token-1", "fp-2", 300))
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_charging_pending_sweep_expires_booking_and_releases_capacity():
    pool, database, user = _values()
    expired_id = uuid4()
    pool.connection.expired_rows = [{"id": expired_id, "slot_id": pool.connection.slot_id}]

    asyncio.run(database.create_pending_booking(
        user, pool.connection.slot_id, uuid4(), Decimal("50.00"), "lock:token-1", "fp-1", 300))

    assert pool.connection.slot_booked_updates == 1
    assert pool.connection.events.count(expired_id) == 1


def test_attach_order_and_mark_unknown_transition_payment_state():
    pool, database, user = _values()
    booking, created = asyncio.run(database.create_pending_booking(
        user, pool.connection.slot_id, uuid4(), Decimal("50.00"), "lock:token-1", "fp-1", 300))
    assert created is True
    payment_id = booking["payment_id"]

    asyncio.run(database.attach_order(payment_id, "order_charging_1"))
    assert pool.connection.payment_state == {"order_state": "ready", "razorpay_order_id": "order_charging_1"}
    with pytest.raises(ApiError) as error:
        asyncio.run(database.attach_order(payment_id, "order_charging_2"))
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "PAYMENT_ORDER_STATE_CHANGED"

    pool.connection.payment_state = {"order_state": "creating", "razorpay_order_id": None}
    asyncio.run(database.mark_order_unknown(payment_id))
    assert pool.connection.payment_state["order_state"] == "reconciliation_required"
