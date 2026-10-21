from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from redis.exceptions import RedisError

from app.auth.dependencies import CurrentUser
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.dependencies import get_redis
from app.core.config import Settings, get_settings
from app.core.responses import success
from app.vendors.portal_schemas import (
    ServiceCreate,
    ServicePatch,
    SlotCreate,
    SlotPatch,
    VendorProfileCreate,
    VendorProfilePatch,
)
from app.disputes.schemas import DisputeMessage

router = APIRouter(prefix="/vendor", tags=["vendor-portal"])


async def _vendor_id(user: CurrentUser, database: DatabaseDependency) -> UUID:
    vendor_id = await database.vendor_id_for_owner(user.id)
    if vendor_id is None:
        raise ApiError(404, "VENDOR_PROFILE_NOT_FOUND", "No vendor profile is linked to this account")
    return vendor_id


@router.get("/profile")
async def get_vendor_profile(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    profile = await database.vendor_profile_for_owner(user.id)
    if profile is None:
        raise ApiError(404, "VENDOR_PROFILE_NOT_FOUND", "No vendor profile is linked to this account")
    return success(profile)


@router.post("/profile")
async def create_vendor_profile(
    payload: VendorProfileCreate, user: CurrentUser, database: DatabaseDependency
) -> dict[str, Any]:
    if await database.vendor_id_for_owner(user.id) is not None:
        raise ApiError(409, "VENDOR_PROFILE_EXISTS", "This account already has a vendor profile")
    profile = await database.create_vendor_profile(user.id, payload.model_dump())
    return success(profile, "Vendor profile submitted for verification")


@router.patch("/profile")
async def patch_vendor_profile(
    payload: VendorProfilePatch, user: CurrentUser, database: DatabaseDependency
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    profile = await database.update_vendor_profile(
        user.id, vendor_id, payload.model_dump(exclude_unset=True)
    )
    if profile is None:
        raise ApiError(404, "VENDOR_PROFILE_NOT_FOUND", "Vendor profile was not found")
    return success(profile, "Vendor profile updated")


@router.get("/dashboard")
async def get_vendor_dashboard(
    user: CurrentUser, database: DatabaseDependency, redis=Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    dashboard = await database.vendor_dashboard(user.id, vendor_id)
    capacity_slots = await database.vendor_available_capacity_slots(user.id, vendor_id)
    try:
        lock_values = await redis.mget(*[f"{settings.booking_lock_prefix}{slot['id']}" for slot in capacity_slots]) if capacity_slots else []
    except RedisError as exc:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Dashboard availability could not be refreshed") from exc
    held_capacity = sum(
        int(slot["available_capacity"]) for slot, lock_value in zip(capacity_slots, lock_values) if lock_value
    )
    dashboard["metrics"]["available_capacity"] = max(
        0, int(dashboard["metrics"]["available_capacity"]) - held_capacity
    )
    return success(dashboard)


@router.get("/bookings")
async def list_vendor_bookings(
    user: CurrentUser,
    database: DatabaseDependency,
    status: str | None = Query(default=None, pattern="^(pending|confirmed|cancelled|completed|expired)$"),
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    return success(await database.vendor_bookings(user.id, vendor_id, status))


@router.get("/bookings/{booking_id}")
async def get_vendor_booking(
    booking_id: UUID, user: CurrentUser, database: DatabaseDependency
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    booking = await database.vendor_booking(user.id, vendor_id, booking_id)
    if booking is None:
        raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
    return success(booking)


@router.post("/bookings/{booking_id}/accept")
async def accept_vendor_booking(
    booking_id: UUID, user: CurrentUser, database: DatabaseDependency
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    booking = await database.vendor_booking_action(user.id, vendor_id, booking_id, "accept")
    return success(booking, "Paid booking accepted")


@router.post("/bookings/{booking_id}/complete")
async def complete_vendor_booking(
    booking_id: UUID, user: CurrentUser, database: DatabaseDependency
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    booking = await database.vendor_booking_action(user.id, vendor_id, booking_id, "complete")
    return success(booking, "Booking marked complete")


@router.get("/disputes")
async def list_vendor_disputes(
    user: CurrentUser,
    database: DatabaseDependency,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    return success(await database.vendor_disputes(vendor_id, limit, offset))


@router.get("/disputes/{dispute_id}")
async def get_vendor_dispute(dispute_id: UUID, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    result = await database.vendor_dispute(vendor_id, dispute_id)
    if result is None:
        raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
    return success(result)


@router.post("/disputes/{dispute_id}/messages")
async def add_vendor_dispute_message(
    dispute_id: UUID,
    payload: DisputeMessage,
    request: Request,
    user: CurrentUser,
    database: DatabaseDependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
) -> dict[str, Any]:
    if not idempotency_key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "An Idempotency-Key header is required")
    vendor_id = await _vendor_id(user, database)
    result = await database.add_vendor_dispute_message(vendor_id, user.id, dispute_id, payload.message, idempotency_key,
        {"ip": request.client.host if request.client else None,
         "user_agent": request.headers.get("user-agent", "")[:500],
         "request_id": request.headers.get("x-request-id", "")[:120]})
    return success(result, "Response added to dispute")


@router.get("/availability")
async def get_vendor_availability(
    user: CurrentUser, database: DatabaseDependency, redis=Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    slots = await database.vendor_slots_for_owner(user.id, vendor_id)
    try:
        lock_values = await redis.mget(*[f"{settings.booking_lock_prefix}{slot['id']}" for slot in slots]) if slots else []
    except RedisError as exc:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Availability lock state could not be loaded") from exc
    for slot, lock_value in zip(slots, lock_values):
        slot["locked"] = bool(lock_value)
    return success(slots)


@router.post("/availability")
async def create_vendor_slot(
    payload: SlotCreate, user: CurrentUser, database: DatabaseDependency
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    slot = await database.create_vendor_slot(user.id, vendor_id, payload.model_dump())
    return success(slot, "Availability slot created")


@router.patch("/availability/{slot_id}")
async def update_vendor_slot(
    slot_id: UUID, payload: SlotPatch, user: CurrentUser, database: DatabaseDependency,
    redis=Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    try:
        locked = bool(await redis.get(f"{settings.booking_lock_prefix}{slot_id}"))
    except RedisError as exc:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Slot lock state could not be checked") from exc
    slot = await database.update_vendor_slot(
        user.id, vendor_id, slot_id, payload.model_dump(exclude_unset=True), slot_locked=locked
    )
    return success(slot, "Availability slot updated")


@router.delete("/availability/{slot_id}")
async def delete_vendor_slot(
    slot_id: UUID, user: CurrentUser, database: DatabaseDependency,
    redis=Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    try:
        locked = bool(await redis.get(f"{settings.booking_lock_prefix}{slot_id}"))
    except RedisError as exc:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Slot lock state could not be checked") from exc
    if locked:
        raise ApiError(409, "SLOT_TEMPORARILY_LOCKED", "A driver is holding this slot for booking")
    await database.delete_vendor_slot(user.id, vendor_id, slot_id)
    return success({"id": str(slot_id)}, "Availability slot deleted")


@router.get("/services")
async def list_vendor_services(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    return success(await database.vendor_services(user.id, vendor_id))


@router.post("/services")
async def create_vendor_service(
    payload: ServiceCreate, user: CurrentUser, database: DatabaseDependency
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    service = await database.create_vendor_service(user.id, vendor_id, payload.model_dump())
    return success(service, "Service created")


@router.patch("/services/{service_id}")
async def patch_vendor_service(
    service_id: UUID, payload: ServicePatch, user: CurrentUser, database: DatabaseDependency
) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    service = await database.update_vendor_service(
        user.id, vendor_id, service_id, payload.model_dump(exclude_unset=True)
    )
    if service is None:
        raise ApiError(404, "SERVICE_NOT_FOUND", "Service was not found")
    return success(service, "Service updated")


@router.get("/revenue")
async def get_vendor_revenue(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    return success(await database.vendor_revenue(user.id, vendor_id))
