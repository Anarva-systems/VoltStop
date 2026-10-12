from typing import Annotated

import asyncpg
import httpx
from fastapi import Depends, Request

from app.core.errors import ApiError
from app.core.config import Settings, get_settings


async def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


async def get_db_pool(request: Request) -> asyncpg.Pool:
    pool = request.app.state.db_pool
    if pool is None:
        raise ApiError(503, "DATABASE_UNAVAILABLE", "Database is not configured")
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
