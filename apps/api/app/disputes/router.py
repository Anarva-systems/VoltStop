from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request

from app.auth.dependencies import CurrentUser
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success
from app.disputes.schemas import CustomerDisputeCreate, DisputeMessage

router = APIRouter(prefix="/disputes", tags=["disputes"])


def _metadata(request: Request) -> dict[str, Any]:
    return {"ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", "")[:500],
            "request_id": request.headers.get("x-request-id", "")[:120]}


@router.post("", status_code=201)
async def create_dispute(
    payload: CustomerDisputeCreate,
    request: Request,
    user: CurrentUser,
    database: DatabaseDependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
) -> dict[str, Any]:
    if not idempotency_key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "An Idempotency-Key header is required")
    result, created = await database.create_customer_dispute(
        user.id, payload.booking_id, payload.reason, payload.description, idempotency_key, _metadata(request),
    )
    return success(result, "Dispute created" if created else "Existing dispute returned")


@router.get("")
async def list_disputes(
    user: CurrentUser,
    database: DatabaseDependency,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    return success(await database.customer_disputes(user.id, limit, offset))


@router.get("/{dispute_id}")
async def get_dispute(dispute_id: UUID, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    result = await database.customer_dispute(user.id, dispute_id)
    if result is None:
        raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
    return success(result)


@router.post("/{dispute_id}/messages")
async def add_customer_message(
    dispute_id: UUID,
    payload: DisputeMessage,
    request: Request,
    user: CurrentUser,
    database: DatabaseDependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
) -> dict[str, Any]:
    if not idempotency_key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "An Idempotency-Key header is required")
    result = await database.add_customer_dispute_message(user.id, dispute_id, payload.message, idempotency_key, _metadata(request))
    return success(result, "Message added to dispute")
