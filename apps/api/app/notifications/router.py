import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request

from app.auth.dependencies import CurrentUser
from app.core.config import get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.rate_limit import user_rate_limit
from app.core.responses import success
from app.notifications.push import PushConfigurationError, PushDispatcher, build_sender
from app.notifications.schemas import PushTokenRegister

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)


@router.get("/push-status")
async def push_status(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    """Report whether this account can receive push, and why not if it cannot."""
    settings = get_settings()
    async with database.pool.acquire() as conn:
        devices = await conn.fetchval(
            "select count(*) from public.user_push_tokens where user_id=$1 and provider='fcm'", user.id
        )
    return success({
        "provider": "fcm",
        "configured": bool(settings.fcm_service_account_json.strip()),
        "project_configured": bool(settings.fcm_project_id.strip()),
        "registered_devices": int(devices or 0),
    })


async def _drain_push(request: Request, database: DatabaseDependency, user_id: UUID) -> None:
    settings = get_settings()
    try:
        sender = build_sender(
            request.app.state.http_client,
            project_id=settings.fcm_project_id,
            service_account_json=settings.fcm_service_account_json,
        )
    except PushConfigurationError as exc:
        logger.warning("Push dispatch misconfigured: %s", exc)
        return
    await PushDispatcher(database.pool, sender).dispatch(user_id=user_id, limit=5)


@router.put("/push-token")
async def register_push_token(
    request: Request,
    payload: PushTokenRegister,
    user: CurrentUser,
    database: DatabaseDependency,
    background: BackgroundTasks,
    _limit: None = Depends(user_rate_limit("push-token-register", 30, 3600)),
) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow(
            """insert into public.user_push_tokens(user_id, provider, token, platform)
               values ($1,'fcm',$2,$3)
               on conflict (provider, token)
                 do update set user_id = excluded.user_id, platform = excluded.platform,
                               last_seen_at = now(), updated_at = now()
               returning id, user_id, platform, last_seen_at""",
            user.id, payload.token, payload.platform,
        )
    if row is None:
        raise ApiError(500, "PUSH_TOKEN_NOT_SAVED", "Push token could not be registered")
    background.add_task(_drain_push, request, database, user.id)
    return success(dict(row), "Push token registered")


@router.delete("/push-token")
async def unregister_push_token(
    user: CurrentUser,
    database: DatabaseDependency,
    token: str = Query(min_length=16, max_length=512),
) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        result = await conn.execute(
            "delete from public.user_push_tokens where user_id=$1 and provider='fcm' and token=$2",
            user.id, token,
        )
    removed = int(result.split()[-1]) if result.startswith("DELETE ") else 0
    if removed == 0:
        raise ApiError(404, "PUSH_TOKEN_NOT_FOUND", "Push token was not registered for this account")
    return success({"removed": removed}, "Push token removed")


@router.get("")
async def list_notifications(request: Request, user: CurrentUser, database: DatabaseDependency,
                             background: BackgroundTasks,
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
    # The feed is the one touchpoint every client already polls, so it also drains this
    # account's push queue. With no FCM credentials the drain costs one settings read.
    background.add_task(_drain_push, request, database, user.id)
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
