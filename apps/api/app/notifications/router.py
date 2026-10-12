from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.auth.dependencies import CurrentUser
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(user: CurrentUser, database: DatabaseDependency,
                             unread_only: bool = False,
                             limit: int = Query(default=50, ge=1, le=100),
                             offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        total = await conn.fetchval("select count(*) from public.notifications where user_id=$1 and (not $2 or read_at is null)", user.id, unread_only)
        rows = await conn.fetch(
            """select id,booking_id,type,title,message,read_at,created_at from public.notifications
               where user_id=$1 and (not $2 or read_at is null) order by created_at desc limit $3 offset $4""",
            user.id, unread_only, limit, offset,
        )
        unread = await conn.fetchval("select count(*) from public.notifications where user_id=$1 and read_at is null", user.id)
    return success({"items": [dict(row) for row in rows], "total": total, "unread": unread, "limit": limit, "offset": offset})


@router.patch("/{notification_id}/read")
async def mark_read(notification_id: UUID, user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            "update public.notifications set read_at=coalesce(read_at,now()) where id=$1 and user_id=$2 returning id,read_at",
            notification_id, user.id,
        )
    if row is None:
        raise ApiError(404, "NOTIFICATION_NOT_FOUND", "Notification was not found")
    return success(dict(row), "Notification marked as read")


@router.post("/read-all")
async def mark_all_read(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        result = await conn.execute("update public.notifications set read_at=now() where user_id=$1 and read_at is null", user.id)
    count = int(result.split()[-1]) if result.startswith("UPDATE ") else 0
    return success({"updated": count}, "Notifications marked as read")
