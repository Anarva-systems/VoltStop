import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import asyncpg

from app.core.database import Database
from app.core.errors import ApiError


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


class _WindowConnection:
    """Every charging_slots write collides with the overlap exclusion constraint."""

    def __init__(self):
        self.owner_id, self.vendor_id, self.slot_id = uuid4(), uuid4(), uuid4()
        self.start = datetime.now(timezone.utc) + timedelta(days=1)
        self.end = self.start + timedelta(hours=2)

    def transaction(self):
        return _Transaction()

    async def fetchval(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.vendor_services" in normalized:
            return True
        if "from public.bookings" in normalized:
            return 0
        raise AssertionError(f"Unexpected fetchval query: {normalized}")

    async def fetchrow(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "insert into public.charging_slots" in normalized or "update public.charging_slots" in normalized:
            raise asyncpg.ExclusionViolationError(
                "conflicting key value violates exclusion constraint charging_slots_no_overlapping_window"
            )
        if "from public.charging_slots cs join public.vendors v" in normalized:
            return {
                "id": self.slot_id, "vendor_id": self.vendor_id,
                "slot_start_time": self.start, "slot_end_time": self.end,
                "capacity": 2, "price_inr": Decimal("500.00"),
                "status": "available", "service_type": "charging",
            }
        raise AssertionError(f"Unexpected fetchrow query: {normalized}")

    async def fetch(self, query, *args):
        raise AssertionError(f"Unexpected fetch query: {query}")

    async def execute(self, *args):
        return "OK"


class _SweepConnection:
    def __init__(self, due=None):
        self.owner_id = uuid4()
        self.slot_a, self.slot_b = uuid4(), uuid4()
        self.due = [] if due is None else due
        self.released_slots = []
        self.expired_events = 0

    def transaction(self):
        return _Transaction()

    async def fetch(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.bookings" in normalized and "hold_expires_at <= now()" in normalized:
            return [{"id": booking_id, "slot_id": slot_id} for booking_id, slot_id in self.due]
        raise AssertionError(f"Unexpected fetch query: {normalized}")

    async def execute(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "insert into public.booking_events" in normalized:
            self.expired_events += 1
            return "INSERT 0 1"
        if "set status='available'" in normalized:
            self.released_slots.append(args[0])
            return "UPDATE 1"
        if "set status='expired'" in normalized:
            return "UPDATE 1"
        raise AssertionError(f"Unexpected execute query: {normalized}")


def test_overlapping_slot_creation_surfaces_the_exclusion_constraint_as_409():
    async def run():
        connection = _WindowConnection()
        try:
            await Database(_Pool(connection)).create_vendor_slot(connection.owner_id, connection.vendor_id, {
                "slot_start_time": connection.start,
                "slot_end_time": connection.end,
                "capacity": 2,
                "price_inr": Decimal("500.00"),
                "service_type": "charging",
            })
        except ApiError as error:
            return error
        raise AssertionError("Expected the exclusion violation to be translated")

    error = asyncio.run(run())
    assert error.status_code == 409
    assert error.detail["code"] == "SLOT_WINDOW_OVERLAPS"


def test_moving_a_slot_into_another_window_surfaces_the_same_conflict():
    async def run():
        connection = _WindowConnection()
        try:
            await Database(_Pool(connection)).update_vendor_slot(
                connection.owner_id,
                connection.vendor_id,
                connection.slot_id,
                {
                    "slot_start_time": connection.start + timedelta(hours=1),
                    "slot_end_time": connection.end + timedelta(hours=1),
                },
            )
        except ApiError as error:
            return error
        raise AssertionError("Expected the exclusion violation to be translated")

    error = asyncio.run(run())
    assert error.status_code == 409
    assert error.detail["code"] == "SLOT_WINDOW_OVERLAPS"


def test_hold_sweep_expires_holds_and_frees_their_slots():
    async def run():
        first, second = uuid4(), uuid4()
        connection = _SweepConnection(due=[(first, uuid4()), (second, uuid4())])
        expired = await Database(_Pool(connection)).expire_due_booking_holds()
        return connection, expired

    connection, expired = asyncio.run(run())
    assert expired == 2
    assert connection.expired_events == 2
    assert len(connection.released_slots) == 2


def test_hold_sweep_is_a_no_op_when_nothing_is_due():
    async def run():
        connection = _SweepConnection()
        return await Database(_Pool(connection)).expire_due_booking_holds()

    assert asyncio.run(run()) == 0
