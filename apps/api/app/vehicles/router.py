from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header

from app.auth.dependencies import CurrentUser
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success
from app.vehicles.schemas import VehicleCreate, VehiclePatch

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _idempotency_key(value: str | None) -> str:
    key = (value or "").strip()
    if not 8 <= len(key) <= 200:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "A valid Idempotency-Key header is required")
    return key


@router.get("")
async def list_vehicles(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    return success(await database.driver_vehicles(user.id))


@router.post("")
async def create_vehicle(
    payload: VehicleCreate, user: CurrentUser, database: DatabaseDependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    result = await database.create_driver_vehicle(user.id, payload.model_dump(), _idempotency_key(idempotency_key))
    return success(result, "Vehicle saved")


@router.get("/{vehicle_id}")
async def get_vehicle(vehicle_id: UUID, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    result = await database.driver_vehicle(user.id, vehicle_id)
    if result is None:
        raise ApiError(404, "VEHICLE_NOT_FOUND", "Vehicle was not found")
    return success(result)


@router.patch("/{vehicle_id}")
async def update_vehicle(
    vehicle_id: UUID, payload: VehiclePatch, user: CurrentUser, database: DatabaseDependency,
) -> dict[str, Any]:
    try:
        changes = payload.changes()
    except ValueError as exc:
        raise ApiError(422, "EMPTY_PATCH", str(exc)) from exc
    result = await database.patch_driver_vehicle(user.id, vehicle_id, changes)
    if result is None:
        raise ApiError(404, "VEHICLE_NOT_FOUND", "Vehicle was not found")
    return success(result, "Vehicle updated")


@router.post("/{vehicle_id}/default")
async def select_default_vehicle(
    vehicle_id: UUID, user: CurrentUser, database: DatabaseDependency,
) -> dict[str, Any]:
    result = await database.select_default_driver_vehicle(user.id, vehicle_id)
    if result is None:
        raise ApiError(404, "VEHICLE_NOT_FOUND", "Vehicle was not found")
    return success(result, "Active vehicle updated")


@router.delete("/{vehicle_id}")
async def delete_vehicle(vehicle_id: UUID, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    deleted = await database.delete_driver_vehicle(user.id, vehicle_id)
    if not deleted:
        raise ApiError(404, "VEHICLE_NOT_FOUND", "Vehicle was not found")
    return success({"deleted": True}, "Vehicle deleted")
