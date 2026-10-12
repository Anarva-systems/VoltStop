from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query


from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("/nearby")
async def nearby_vendors(
    database: DatabaseDependency,
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_km: float = Query(gt=0, le=200),
) -> dict[str, Any]:
    vendors = await database.nearby_vendors(lat, lng, radius_km)
    return success(vendors)


@router.get("/{vendor_id}")
async def vendor_details(vendor_id: UUID, database: DatabaseDependency) -> dict[str, Any]:
    vendor = await database.vendor(vendor_id)
    if vendor is None:
        raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor was not found")
    return success(vendor)


@router.get("/{vendor_id}/slots")
async def vendor_slots(vendor_id: UUID, database: DatabaseDependency) -> dict[str, Any]:
    slots = await database.vendor_slots(vendor_id)
    if slots is None:
        raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor was not found")
    return success(slots)
