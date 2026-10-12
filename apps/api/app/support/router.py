from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from app.admin.auth import AdminContext, require_permission
from app.auth.dependencies import CurrentUser
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success
from app.support.repository import SupportRepository
from app.support.schemas import TicketAdminPatch, TicketCreate, TicketMessageCreate

router = APIRouter(prefix="/support", tags=["support"])
admin_router = APIRouter(prefix="/admin/support", tags=["admin-support"])


def _key(value: str | None) -> str:
    if not value:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "An Idempotency-Key header is required")
    return value


@router.get("")
async def list_my_tickets(user: CurrentUser, database: DatabaseDependency,
                          limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return success(await SupportRepository(database.pool).list_user(user.id, limit, offset))


@router.post("", status_code=201)
async def create_customer_ticket(payload: TicketCreate, user: CurrentUser, database: DatabaseDependency,
                                 idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128)) -> dict[str, Any]:
    value = await SupportRepository(database.pool).create(user.id, payload.category, payload.subject, payload.message,
                                                          _key(idempotency_key), booking_id=payload.booking_id)
    return success(value, "Support request created")


@router.post("/vendor", status_code=201)
async def create_vendor_ticket(payload: TicketCreate, user: CurrentUser, database: DatabaseDependency,
                               idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128)) -> dict[str, Any]:
    value = await SupportRepository(database.pool).create(user.id, payload.category, payload.subject, payload.message,
                                                          _key(idempotency_key), vendor_context=True, booking_id=payload.booking_id)
    return success(value, "Support request created")


@router.get("/{ticket_id}")
async def ticket_detail(ticket_id: UUID, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    result = await SupportRepository(database.pool).detail_for_user(user.id, ticket_id)
    if result is None:
        raise ApiError(404, "SUPPORT_TICKET_NOT_FOUND", "Support ticket was not found")
    return success(result)


@router.post("/{ticket_id}/messages")
async def reply(ticket_id: UUID, payload: TicketMessageCreate, user: CurrentUser, database: DatabaseDependency,
                idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128)) -> dict[str, Any]:
    result = await SupportRepository(database.pool).add_message(user.id, ticket_id, payload.message, _key(idempotency_key))
    return success(result, "Reply recorded")


@admin_router.get("")
async def list_tickets(_admin: Annotated[AdminContext, Depends(require_permission("support:read"))], database: DatabaseDependency,
                       status: str | None = Query(default=None, pattern="^(open|in_progress|waiting_on_customer|resolved|closed)$"),
                       priority: str | None = Query(default=None, pattern="^(normal|high|urgent)$"),
                       q: str | None = Query(default=None, max_length=160),
                       limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return success(await SupportRepository(database.pool).admin_list(status, priority, q, limit, offset))


@admin_router.get("/{ticket_id}")
async def admin_detail(ticket_id: UUID, _admin: Annotated[AdminContext, Depends(require_permission("support:read"))],
                       database: DatabaseDependency) -> dict[str, Any]:
    result = await SupportRepository(database.pool).detail_admin(ticket_id)
    if result is None:
        raise ApiError(404, "SUPPORT_TICKET_NOT_FOUND", "Support ticket was not found")
    return success(result)


@admin_router.post("/{ticket_id}/messages")
async def admin_reply(ticket_id: UUID, payload: TicketMessageCreate,
                      admin: Annotated[AdminContext, Depends(require_permission("support:manage"))], database: DatabaseDependency,
                      idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", min_length=8, max_length=128),
                      internal: bool = Query(default=False)) -> dict[str, Any]:
    return success(await SupportRepository(database.pool).add_message(admin.user_id, ticket_id, payload.message,
                                                                      _key(idempotency_key), admin=True, internal=internal),
                   "Internal note recorded" if internal else "Support reply recorded")


@admin_router.patch("/{ticket_id}")
async def update_ticket(ticket_id: UUID, payload: TicketAdminPatch, admin: Annotated[AdminContext, Depends(require_permission("support:manage"))],
                        database: DatabaseDependency) -> dict[str, Any]:
    changes = payload.model_dump(exclude_unset=True)
    if len(changes) == 1:
        raise ApiError(422, "EMPTY_SUPPORT_UPDATE", "A status, priority, or assignee change is required")
    return success(await SupportRepository(database.pool).admin_update(admin.user_id, admin.role_name, ticket_id, changes), "Support ticket updated")
