import secrets
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from redis.exceptions import RedisError

from app.auth.dependencies import CurrentUser
from app.core.config import Settings, get_settings

from app.core.database_dependency import DatabaseDependency
from app.core.dependencies import get_redis
from app.core.errors import ApiError
from app.core.responses import success
from app.bookings.schemas import CreateBookingRequest, SlotLockRequest
from app.payments.service import RazorpayGateway

router = APIRouter(prefix="/bookings", tags=["bookings"])
LOCK_PREFIX = "voltstop:booking-lock:"


def payment_gateway(request: Request, settings: Settings = Depends(get_settings)) -> RazorpayGateway:
    return RazorpayGateway(request.app.state.http_client, settings)


def _lock_key(slot_id: UUID) -> str:
    return f"{LOCK_PREFIX}{slot_id}"


async def _release_lock(redis: Any, key: str, expected: str) -> None:
    try:
        await redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            1,
            key,
            expected,
        )
    except RedisError:
        # The lock is bounded by its TTL; a release failure must not hide a committed booking.
        return


@router.post("/lock")
async def lock_slot(
    payload: SlotLockRequest,
    user: CurrentUser,
    database: DatabaseDependency,
    redis=Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    slot = await database.slot(payload.slot_id)
    if slot is None:
        raise ApiError(404, "SLOT_NOT_FOUND", "Available slot was not found")
    lock_token = secrets.token_urlsafe(32)
    lock_value = f"{user.id}:{lock_token}"
    try:
        acquired = await redis.set(
            _lock_key(payload.slot_id), lock_value,
            nx=True,
            ex=settings.booking_lock_ttl_seconds,
        )
    except RedisError as exc:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Booking lock service is unavailable") from exc
    if not acquired:
        raise ApiError(409, "SLOT_LOCKED", "Another driver is reserving this slot")
    return success(
        {"slot_id": str(payload.slot_id), "lock_token": lock_token,
         "expires_in_seconds": settings.booking_lock_ttl_seconds},
        "Slot temporarily reserved",
    )


@router.post("")
async def create_booking(
    payload: CreateBookingRequest,
    user: CurrentUser,
    database: DatabaseDependency,
    redis=Depends(get_redis),
    gateway: RazorpayGateway = Depends(payment_gateway),
) -> dict[str, Any]:
    key = _lock_key(payload.slot_id)
    try:
        lock_value = await redis.get(key)
    except RedisError as exc:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Booking lock service is unavailable") from exc
    expected_value = f"{user.id}:{payload.lock_token}"
    if isinstance(lock_value, bytes):
        lock_value = lock_value.decode()
    if not lock_value or not secrets.compare_digest(str(lock_value), expected_value):
        raise ApiError(409, "SLOT_LOCK_EXPIRED", "Slot lock is missing, expired, or belongs to another user")

    try:
        slot = await database.slot(payload.slot_id)
        if slot is None:
            raise ApiError(409, "SLOT_UNAVAILABLE", "Slot is no longer available")
        booking_id = uuid4()
        payment_order = await gateway.create_order(booking_id, Decimal(slot["price_inr"]))
        booking = await database.create_pending_booking(
            user.id,
            payload.slot_id,
            booking_id,
            payment_order["order_id"],
            Decimal(slot["price_inr"]),
        )
    finally:
        await _release_lock(redis, key, expected_value)

    booking["payment"] = {
        "order_id": payment_order["order_id"],
        "amount_paise": payment_order["amount_paise"],
        "currency": payment_order["currency"],
        "key_id": payment_order["key_id"],
        "status": "pending",
    }
    return success(booking, "Booking created; payment confirmation is pending")


@router.get("")
async def list_bookings(
    user: CurrentUser,
    database: DatabaseDependency,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return success(await database.bookings(user.id, limit, offset))


@router.get("/{booking_id}")
async def get_booking(
    booking_id: UUID,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    booking = await database.booking(user.id, booking_id)
    if booking is None:
        raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
    return success(booking)


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: UUID,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    booking = await database.cancel_booking(user.id, booking_id)
    if booking is None:
        raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
    return success(booking, "Booking cancelled")



