import asyncio
import logging
from typing import Annotated

import asyncpg
import httpx
from fastapi import Depends, Request

from app.core.errors import ApiError
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


async def get_db_pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        database_url = get_settings().database_url
        if not database_url:
            raise ApiError(503, "DATABASE_UNAVAILABLE", "Database is not configured")

        # Some serverless ASGI adapters do not run FastAPI lifespan hooks for
        # each warm function instance. Initialize the pool on first use too.
        lock = getattr(request.app.state, "db_pool_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            request.app.state.db_pool_lock = lock
        async with lock:
            pool = getattr(request.app.state, "db_pool", None)
            if pool is None:
                try:
                    settings = get_settings()
                    pool = await asyncpg.create_pool(
                        database_url,
                        min_size=settings.database_pool_min_size,
                        max_size=settings.database_pool_max_size,
                        command_timeout=10,
                    )
                    request.app.state.db_pool = pool
                except Exception as exc:
                    logger.exception("Database pool initialization failed")
                    raise ApiError(
                        503,
                        "DATABASE_UNAVAILABLE",
                        "Database is temporarily unavailable",
                    ) from exc
    return pool


async def get_settings_dependency() -> Settings:
    return get_settings()


async def get_redis(request: Request):
    redis_client = request.app.state.redis
    if redis_client is None:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Booking lock service is not configured")
    return redis_client


HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]
DbPool = Annotated[asyncpg.Pool, Depends(get_db_pool)]
SettingsDependency = Annotated[Settings, Depends(get_settings_dependency)]
