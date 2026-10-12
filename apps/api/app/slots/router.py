from typing import Any
from uuid import UUID

from fastapi import APIRouter


from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success

router = APIRouter(prefix="/slots", tags=["slots"])


@router.get("/{slot_id}")
async def get_slot(slot_id: UUID, database: DatabaseDependency) -> dict[str, Any]:
    slot = await database.slot(slot_id)
    if slot is None:
        raise ApiError(404, "SLOT_NOT_FOUND", "Available slot was not found")
    return success(slot)
