import asyncio
import logging
import os
from typing import Annotated
from urllib.parse import urlsplit

import asyncpg
import httpx
from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.errors import ApiError
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


async def get_http_client(request: Request) -> httpx.AsyncClient:
    client = getattr(request.app.state, "http_client", None)
    if client is not None:
        return client

    # Keep outbound clients available when a serverless ASGI adapter omits the
    # application lifespan hooks for a warm function instance.
    lock = getattr(request.app.state, "http_client_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.http_client_lock = lock
    async with lock:
        client = getattr(request.app.state, "http_client", None)
        if client is None:
            client = httpx.AsyncClient(timeout=httpx.Timeout(8.0))
            request.app.state.http_client = client
    return client


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
                    # Supabase's shared transaction pooler (port 6543) does not
                    # support prepared statements. asyncpg enables its statement
                    # cache by default, so disable it when using that endpoint.
                    database_port = urlsplit(database_url).port
                    statement_cache_size = 0 if database_port == 6543 else 100
                    serverless = os.getenv("VERCEL") == "1" or bool(os.getenv("VERCEL_ENV"))
                    pool_max_size = (
                        min(settings.database_pool_max_size, 1)
                        if serverless
                        else settings.database_pool_max_size
                    )
                    pool = await asyncpg.create_pool(
                        database_url,
                        min_size=min(settings.database_pool_min_size, pool_max_size),
                        max_size=pool_max_size,
                        command_timeout=10,
                        statement_cache_size=statement_cache_size,
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
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is not None:
        return redis_client

    settings = get_settings()
    if not settings.redis_enabled or not settings.redis_url:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Booking lock service is not configured")

    # Some serverless ASGI adapters can skip lifespan initialization on a warm
    # function instance. Initialize the shared Redis client once on first use.
    lock = getattr(request.app.state, "redis_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.redis_lock = lock
    async with lock:
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client is None:
            try:
                redis_client = Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                request.app.state.redis = redis_client
            except Exception as exc:
                logger.exception("Redis client initialization failed")
                raise ApiError(
                    503,
                    "LOCK_SERVICE_UNAVAILABLE",
                    "Booking lock service is temporarily unavailable",
                ) from exc
    return redis_client


HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]
DbPool = Annotated[asyncpg.Pool, Depends(get_db_pool)]
SettingsDependency = Annotated[Settings, Depends(get_settings_dependency)]
