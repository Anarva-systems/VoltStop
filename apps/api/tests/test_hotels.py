import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ApiError
from app.hotels.repository import HotelRepository
from app.hotels.schemas import ReservationCreate, RoomTypeCreate, RoomTypePatch


def test_reservation_schema_rejects_past_or_inverted_stay():
    room_id = uuid4()
    with pytest.raises(ValidationError):
        ReservationCreate(room_type_id=room_id, check_in=date.today()-timedelta(days=1),
                          check_out=date.today(), guests=1)
    with pytest.raises(ValidationError):
        ReservationCreate(room_type_id=room_id, check_in=date.today()+timedelta(days=1),
                          check_out=date.today()+timedelta(days=32), guests=1)


def test_room_schemas_reject_out_of_range_and_null_mutations():
    with pytest.raises(ValidationError):
        RoomTypeCreate(name="Suite", max_guests=20, base_rate_inr=1000, total_rooms=2)
    with pytest.raises(ValidationError):
        RoomTypePatch(max_guests=None)


class _Transaction:
    def __init__(self, lock): self.lock = lock
    async def __aenter__(self): await self.lock.acquire()
    async def __aexit__(self, *_): self.lock.release()


class _Acquire:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self.conn
    async def __aexit__(self, *_): return False


class _InventoryConnection:
    """Transactional SQL double: concurrent repository calls share one inventory row."""
    def __init__(self):
        self.lock = asyncio.Lock()
        self.available = 1
        self.room_id, self.vendor_id = uuid4(), uuid4()
        self.now = date.today()
        self.reservations = {}

    def transaction(self): return _Transaction(self.lock)
    async def fetch(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.hotel_reservations" in normalized and "hold_expires_at" in normalized:
            return []
        if "from public.hotel_room_inventory" in normalized:
            return [{"stay_date": args[1], "rooms_available": self.available, "nightly_rate_inr": Decimal("1200.00")}] if self.available >= 0 else []
        raise AssertionError(f"Unexpected fetch query: {normalized}")
    async def fetchrow(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.hotel_reservations r left join public.hotel_reservation_payments" in normalized:
            return self.reservations.get((args[0], args[1]))
        if "from public.hotel_room_types r join public.vendors" in normalized and "for update of r" in normalized:
            return {"vendor_id": self.vendor_id, "max_guests": 2, "free_cancellation_hours": 24, "is_active": True,
                    "vendor_active": True, "is_verified": True, "type": "hotel"}
        if "insert into public.hotel_reservations" in normalized:
            row = {"id": uuid4(), "customer_id": args[0], "vendor_id": args[1], "room_type_id": args[2],
                    "check_in": args[3], "check_out": args[4], "guests": args[5], "rooms": args[6],
                    "amount_inr": args[7], "free_cancellation_hours": args[8], "currency": "INR",
                    "status": "payment_pending", "created_at": self.now, "request_fingerprint": args[10]}
            self.reservations[(args[0], args[9])] = row
            return row
        raise AssertionError(f"Unexpected fetchrow query: {normalized}")
    async def fetchval(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "insert into public.hotel_reservation_payments" in normalized: return uuid4()
        if "update public.hotel_room_inventory" in normalized:
            if self.available < args[2]: return None
            self.available -= args[2]
            return self.available
        raise AssertionError(f"Unexpected fetchval query: {normalized}")
    async def execute(self, *_): return "INSERT 0 1"


class _InventoryPool:
    def __init__(self): self.connection = _InventoryConnection()
    def acquire(self): return _Acquire(self.connection)


def test_concurrent_reservations_cannot_overbook_last_room():
    async def run():
        pool = _InventoryPool()
        repository = HotelRepository(pool)
        room_id = pool.connection.room_id
        check_in = date.today()+timedelta(days=2)
        values = {"room_type_id": room_id, "check_in": check_in, "check_out": check_in+timedelta(days=1),
                  "guests": 2, "rooms": 1, "expected_amount_inr": Decimal("1200.00")}
        results = await asyncio.gather(
            repository.create_reservation(uuid4(), values, "customer-reservation-1"),
            repository.create_reservation(uuid4(), values, "customer-reservation-2"),
            return_exceptions=True,
        )
        assert sum(not isinstance(value, Exception) for value in results) == 1
        failure = next(value for value in results if isinstance(value, Exception))
        assert isinstance(failure, ApiError)
        assert failure.status_code == 409
        assert pool.connection.available == 0
    asyncio.run(run())


def test_same_customer_idempotency_key_returns_existing_reservation():
    async def run():
        pool = _InventoryPool()
        repository = HotelRepository(pool)
        customer = uuid4()
        check_in = date.today()+timedelta(days=2)
        values = {"room_type_id": pool.connection.room_id, "check_in": check_in,
                  "check_out": check_in+timedelta(days=1), "guests": 2, "rooms": 1,
                  "expected_amount_inr": Decimal("1200.00")}
        first, created = await repository.create_reservation(customer, values, "retry-safe-key")
        replay, replay_created = await repository.create_reservation(customer, values, "retry-safe-key")
        assert created is True and replay_created is False
        assert first["id"] == replay["id"]
        assert pool.connection.available == 0
    asyncio.run(run())


def test_changed_server_price_does_not_allocate_inventory():
    async def run():
        pool = _InventoryPool()
        repository = HotelRepository(pool)
        check_in = date.today()+timedelta(days=2)
        values = {"room_type_id": pool.connection.room_id, "check_in": check_in,
                  "check_out": check_in+timedelta(days=1), "guests": 2, "rooms": 1,
                  "expected_amount_inr": Decimal("1199.00")}
        with pytest.raises(ApiError) as error:
            await repository.create_reservation(uuid4(), values, "price-change-key")
        assert error.value.status_code == 409
        assert pool.connection.available == 1
    asyncio.run(run())


class _PaymentConnection:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.reservation_id, self.payment_id = uuid4(), uuid4()
        self.order_id, self.provider_payment_id = "order_hotel_test", "pay_hotel_test"
        self.payment = {"id": self.payment_id, "reservation_id": self.reservation_id,
                        "razorpay_order_id": self.order_id, "razorpay_payment_id": None,
                        "amount_inr": Decimal("2400.00"), "currency": "INR", "status": "pending"}
        self.reservation = {"id": self.reservation_id, "customer_id": uuid4(), "status": "payment_pending",
                            "hold_expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)}

    def transaction(self): return _Transaction(self.lock)
    async def fetchrow(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.hotel_reservation_payments where razorpay_order_id=$1" in normalized:
            return self.payment if args[0] == self.order_id else None
        if "from public.hotel_reservations where id=$1 for update" in normalized:
            return self.reservation if args[0] == self.reservation_id else None
        if "from public.hotel_reservation_payments where id=$1 for update" in normalized:
            return self.payment if args[0] == self.payment_id else None
        raise AssertionError(f"Unexpected payment fetchrow query: {normalized}")
    async def fetchval(self, query, *_):
        assert "razorpay_payment_id" in query
        return False
    async def execute(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "update public.hotel_reservation_payments set status=$2" in normalized:
            self.payment.update(status=args[1], razorpay_payment_id=args[2], webhook_verified=True)
        elif "update public.hotel_reservations set status='confirmed'" in normalized:
            self.reservation["status"] = "confirmed"
        else:
            raise AssertionError(f"Unexpected payment execute query: {normalized}")
        return "UPDATE 1"


class _PaymentPool:
    def __init__(self): self.connection = _PaymentConnection()
    def acquire(self): return _Acquire(self.connection)


def test_hotel_capture_is_webhook_authoritative_and_idempotent():
    async def run():
        pool = _PaymentPool()
        repository = HotelRepository(pool)
        accepted = await repository.process_payment_webhook(
            pool.connection.order_id, pool.connection.provider_payment_id, 240000, "INR", True)
        duplicate = await repository.process_payment_webhook(
            pool.connection.order_id, pool.connection.provider_payment_id, 240000, "INR", True)
        assert accepted is True and duplicate is True
        assert pool.connection.reservation["status"] == "confirmed"
        assert pool.connection.payment["status"] == "captured"
        with pytest.raises(ApiError):
            await repository.process_payment_webhook(
                pool.connection.order_id, pool.connection.provider_payment_id, 239999, "INR", True)
    asyncio.run(run())
