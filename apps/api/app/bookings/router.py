import hashlib
import json
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
from app.core.rate_limit import user_rate_limit
from app.core.responses import success
from app.bookings.schemas import CreateBookingRequest, SlotLockRequest
from app.payments.service import RazorpayGateway

router = APIRouter(prefix="/bookings", tags=["bookings"])


def payment_gateway(request: Request, settings: Settings = Depends(get_settings)) -> RazorpayGateway:
    return RazorpayGateway(request.app.state.http_client, settings)


def _lock_key(slot_id: UUID, settings: Settings) -> str:
    return f"{settings.booking_lock_prefix}{slot_id}"


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


def _request_fingerprint(payload: CreateBookingRequest) -> str:
    return hashlib.sha256(
        json.dumps(
            {"slot_id": str(payload.slot_id), "lock_token": payload.lock_token},
            sort_keys=True, separators=(",", ":"),
        ).encode()
    ).hexdigest()


@router.post("/lock")
async def lock_slot(
    payload: SlotLockRequest,
    user: CurrentUser,
    database: DatabaseDependency,
    redis=Depends(get_redis),
    settings: Settings = Depends(get_settings),
    _limit: None = Depends(user_rate_limit("booking-lock", 20, 60)),
) -> dict[str, Any]:
    slot = await database.slot(payload.slot_id)
    if slot is None:
        raise ApiError(404, "SLOT_NOT_FOUND", "Available slot was not found")
    lock_token = secrets.token_urlsafe(32)
    lock_value = f"{user.id}:{lock_token}"
    try:
        acquired = await redis.set(
            _lock_key(payload.slot_id, settings), lock_value,
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
    settings: Settings = Depends(get_settings),
    _limit: None = Depends(user_rate_limit("booking-create", 10, 60)),
) -> dict[str, Any]:
    key = _lock_key(payload.slot_id, settings)
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
        idempotency_key = f"lock:{payload.lock_token}"
        booking, created = await database.create_pending_booking(
            user.id,
            payload.slot_id,
            uuid4(),
            Decimal(slot["price_inr"]),
            idempotency_key,
            _request_fingerprint(payload),
            settings.booking_lock_ttl_seconds,
        )
        if created:
            try:
                payment_order = await gateway.create_order(booking["id"], Decimal(slot["price_inr"]))
            except ApiError:
                await database.mark_order_unknown(booking["payment_id"])
                raise
            try:
                await database.attach_order(booking["payment_id"], payment_order["order_id"])
            except ApiError:
                await database.mark_order_unknown(booking["payment_id"])
                raise
            booking["payment"] = {
                "order_id": payment_order["order_id"],
                "amount_paise": payment_order["amount_paise"],
                "currency": payment_order["currency"],
                "key_id": payment_order["key_id"],
                "status": "pending",
            }
        else:
            if booking.get("order_state") == "reconciliation_required" or not booking.get("razorpay_order_id"):
                raise ApiError(
                    503, "PAYMENT_RECONCILIATION_REQUIRED",
                    "This booking's payment order is awaiting reconciliation; please wait and retry",
                )
            booking["payment"] = {
                "order_id": booking["razorpay_order_id"],
                "amount_paise": int(Decimal(booking["amount_inr"]) * 100),
                "currency": booking.get("currency") or "INR",
                "key_id": settings.razorpay_key_id,
                "status": booking.get("payment_status") or "pending",
            }
    finally:
        await _release_lock(redis, key, expected_value)

    message = ("Booking confirmed" if booking.get("status") == "confirmed"
               else "Booking created; payment confirmation is pending")
    return success(booking, message)


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


@router.get("/{booking_id}/cancellation-quote")
async def booking_cancellation_quote(
    booking_id: UUID,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    quote = await database.booking_cancellation_quote(user.id, booking_id)
    if quote is None:
        raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
    return success(quote, "Cancellation estimate calculated")


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: UUID,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    booking = await database.cancel_booking(user.id, booking_id)
    if booking is None:
        raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
    message = "Booking cancelled; eligible refund awaits finance review" if booking.get("refund_amount_inr", 0) else "Booking cancelled"
    return success(booking, message)



