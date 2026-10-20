from datetime import date, time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request

from app.auth.dependencies import CurrentUser
from app.core.config import Settings, get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success
from app.hotels.repository import HotelRepository
from app.hotels.schemas import InventoryUpsert, QuoteRequest, ReservationCreate, RoomTypeCreate, RoomTypePatch
from app.payments.service import RazorpayGateway
from app.vendors.portal_router import _vendor_id

router = APIRouter(prefix="/hotels", tags=["hotel-reservations"])
vendor_router = APIRouter(prefix="/vendor/hotels", tags=["vendor-hotels"])


def _repo(database: DatabaseDependency) -> HotelRepository:
    return HotelRepository(database.pool)


@router.get("/rooms")
async def rooms(user: CurrentUser, database: DatabaseDependency,
                check_in: date | None = None, check_out: date | None = None,
                guests: int = Query(default=1, ge=1, le=12), rooms: int = Query(default=1, ge=1, le=4),
                vendor_id: UUID | None = None,
                check_in_time: time = time(14, 0), check_out_time: time = time(11, 0)) -> dict[str, Any]:
    return success(await _repo(database).rooms(check_in, check_out, guests, rooms, vendor_id, check_in_time, check_out_time))


@router.get("/rooms/{room_type_id}/availability")
async def room_availability(room_type_id: UUID, check_in: date, check_out: date,
                            user: CurrentUser, database: DatabaseDependency,
                            guests: int = Query(default=1, ge=1, le=12),
                            rooms: int = Query(default=1, ge=1, le=4)) -> dict[str, Any]:
    return success(await _repo(database).quote(room_type_id, check_in, check_out, guests, rooms))


@router.post("/quotes")
async def quote(payload: QuoteRequest, _user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    return success(await _repo(database).quote(**payload.model_dump()))


@router.post("/reservations", status_code=201)
async def create_reservation(payload: ReservationCreate, request: Request, user: CurrentUser,
                             database: DatabaseDependency, settings: Settings = Depends(get_settings),
                             idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128)) -> dict[str, Any]:
    gateway = RazorpayGateway(request.app.state.http_client, settings)
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise ApiError(503, "PAYMENT_UNAVAILABLE", "Razorpay is not configured")
    repo = _repo(database)
    reservation, created = await repo.create_reservation(user.id, payload.model_dump(), idempotency_key)
    payment = await database.hotel_payment_for_reservation(reservation["id"])
    if payment is None:
        raise ApiError(500, "PAYMENT_RECORD_MISSING", "Reservation payment could not be initialized")
    if payment["razorpay_order_id"]:
        order = {"order_id": payment["razorpay_order_id"], "amount_paise": int(payment["amount_inr"] * 100),
                 "currency": payment["currency"], "key_id": settings.razorpay_key_id, "status": payment["status"]}
    elif created and payment["order_state"] == "creating":
        try:
            order = await gateway.create_order(reservation["id"], payment["amount_inr"])
            await repo.attach_order(payment["id"], order["order_id"])
        except Exception:
            # Order creation can time out after the provider accepted it. Never retry
            # blindly; keep the inventory hold bounded and require reconciliation.
            await repo.mark_order_unknown(payment["id"])
            raise
    else:
        raise ApiError(503, "PAYMENT_RECONCILIATION_REQUIRED", "Payment order state is being reconciled; do not retry payment")
    reservation = await repo.reservation(user.id, reservation["id"]) or reservation
    reservation["payment"] = {**order, "status": payment["status"], "webhook_verified": payment["webhook_verified"]}
    return success(reservation, "Reservation held; payment confirmation is pending")


@router.get("/reservations")
async def my_reservations(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    return success(await _repo(database).reservations(user.id))


@router.get("/reservations/{reservation_id}")
async def get_reservation(reservation_id: UUID, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    row = await _repo(database).reservation(user.id, reservation_id)
    if row is None:
        raise ApiError(404, "RESERVATION_NOT_FOUND", "Reservation was not found")
    return success(row)


@router.post("/reservations/{reservation_id}/cancel")
async def cancel_reservation(reservation_id: UUID, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    row = await _repo(database).cancel(user.id, reservation_id)
    if row is None:
        raise ApiError(404, "RESERVATION_NOT_FOUND", "Reservation was not found")
    message = "Cancellation recorded; refund awaits finance review" if row["status"] == "refund_pending" else "Reservation cancelled"
    return success(row, message)


@vendor_router.get("/rooms")
async def vendor_rooms(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).vendor_rooms(user.id, vendor_id))


@vendor_router.post("/rooms", status_code=201)
async def create_room_type(payload: RoomTypeCreate, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).create_room_type(user.id, vendor_id, payload.model_dump()), "Room type created")


@vendor_router.patch("/rooms/{room_type_id}")
async def patch_room_type(room_type_id: UUID, payload: RoomTypePatch, user: CurrentUser,
                          database: DatabaseDependency) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    row = await _repo(database).update_room_type(user.id, vendor_id, room_type_id, payload.model_dump(exclude_unset=True))
    if row is None:
        raise ApiError(404, "ROOM_TYPE_NOT_FOUND", "Room type was not found")
    return success(row, "Room type updated")


@vendor_router.get("/rooms/{room_type_id}/inventory")
async def vendor_inventory(room_type_id: UUID, user: CurrentUser, database: DatabaseDependency,
                           start: date, end: date) -> dict[str, Any]:
    if end <= start or (end-start).days > 366:
        raise ApiError(422, "INVALID_INVENTORY_RANGE", "Inventory range must be 1 to 366 days")
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).inventory(user.id, vendor_id, room_type_id, start, end))


@vendor_router.put("/rooms/{room_type_id}/inventory")
async def put_inventory(room_type_id: UUID, payload: InventoryUpsert, user: CurrentUser,
                        database: DatabaseDependency) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).upsert_inventory(user.id, vendor_id, room_type_id, payload.model_dump()), "Nightly inventory saved")


@vendor_router.get("/reservations")
async def vendor_reservations(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).vendor_reservations(user.id, vendor_id))
