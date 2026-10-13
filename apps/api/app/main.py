import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import httpx
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.bookings.router import router as bookings_router
from app.core.config import get_settings
from app.core.dependencies import get_db_pool
from app.core.errors import ApiError
from app.core.responses import error_response, success
from app.payments.router import router as payments_router
from app.routes.router import router as routes_router
from app.slots.router import router as slots_router
from app.users.router import router as profile_router
from app.vehicles.router import router as vehicles_router
from app.vendors.router import router as vendors_router
from app.vendors.portal_router import router as vendor_portal_router
from app.admin.router import router as admin_router
from app.disputes.router import router as disputes_router
from app.hotels.router import router as hotels_router, vendor_router as vendor_hotels_router
from app.restaurants.router import router as restaurants_router, vendor_router as vendor_restaurants_router, admin_router as admin_restaurant_orders_router
from app.notifications.router import router as notifications_router
from app.admin.portal_pages import router as admin_portal_pages_router
from app.support.router import router as support_router, admin_router as admin_support_router

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(8.0))
    application.state.db_pool = None
    application.state.redis = None
    try:
        if settings.database_url:
            application.state.db_pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=settings.database_pool_min_size,
                max_size=settings.database_pool_max_size,
                command_timeout=10,
            )
        if settings.redis_enabled and settings.redis_url:
            application.state.redis = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        yield
    finally:
        if application.state.db_pool is not None:
            await application.state.db_pool.close()
        if application.state.redis is not None:
            await application.state.redis.aclose()
        await application.state.http_client.aclose()


api_app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)


@api_app.get("/", include_in_schema=False)
async def root_status() -> dict[str, Any]:
    """Provide a minimal deployment status at the API host root."""
    return success({"status": "healthy"}, "VoltStop API is ready")


@api_app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return error_response(
        str(detail.get("code", "HTTP_ERROR")),
        str(detail.get("message", "Request failed")),
        exc.status_code,
    )


@api_app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return error_response("HTTP_ERROR", "Request could not be completed", exc.status_code)


@api_app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": jsonable_encoder(exc.errors()),
            },
        },
    )


@api_app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled API error method=%s path=%s", request.method, request.url.path
    )
    return error_response("INTERNAL_SERVER_ERROR", "An unexpected error occurred", 500)


@api_app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, Any]:
    """Liveness probe: the API process can answer requests."""
    return success({"status": "healthy"}, "API is ready")


@api_app.get("/api/v1/ready", tags=["health"])
async def readiness(request: Request) -> JSONResponse:
    """Readiness probe: the API can serve database-backed live data."""
    try:
        pool = await get_db_pool(request)
        async with pool.acquire() as connection:
            await connection.fetchval("SELECT 1")
    except ApiError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return error_response(
            str(detail.get("code", "DATABASE_UNAVAILABLE")),
            str(detail.get("message", "Database is temporarily unavailable")),
            exc.status_code,
        )
    except Exception:
        logger.exception("Database readiness check failed")
        return error_response(
            "DATABASE_UNAVAILABLE",
            "Database is temporarily unavailable",
            503,
        )
    return JSONResponse(
        status_code=200,
        content=success({"status": "ready", "database": "connected"}, "API and database are ready"),
    )


api_app.include_router(auth_router, prefix="/api/v1")
api_app.include_router(profile_router, prefix="/api/v1")
api_app.include_router(vehicles_router, prefix="/api/v1")
api_app.include_router(vendors_router, prefix="/api/v1")
api_app.include_router(vendor_portal_router, prefix="/api/v1")
api_app.include_router(admin_router, prefix="/api/v1")
api_app.include_router(routes_router, prefix="/api/v1")
api_app.include_router(slots_router, prefix="/api/v1")
api_app.include_router(bookings_router, prefix="/api/v1")
api_app.include_router(payments_router, prefix="/api/v1")
api_app.include_router(disputes_router, prefix="/api/v1")
api_app.include_router(hotels_router, prefix="/api/v1")
api_app.include_router(vendor_hotels_router, prefix="/api/v1")
api_app.include_router(restaurants_router, prefix="/api/v1")
api_app.include_router(vendor_restaurants_router, prefix="/api/v1")
api_app.include_router(admin_restaurant_orders_router, prefix="/api/v1")
api_app.include_router(notifications_router, prefix="/api/v1")
api_app.include_router(admin_portal_pages_router, prefix="/api/v1")
api_app.include_router(support_router, prefix="/api/v1")
api_app.include_router(admin_support_router, prefix="/api/v1")


def create_cors_application(
    application: FastAPI, allowed_origins: list[str]
) -> CORSMiddleware:
    """Wrap the complete ASGI app so error responses also receive CORS headers."""
    cors_application = CORSMiddleware(
        app=application,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type", "Idempotency-Key"],
    )
    # Preserve FastAPI dependency overrides for the existing test suite.
    cors_application.dependency_overrides = application.dependency_overrides
    return cors_application


app = create_cors_application(api_app, settings.vendor_portal_allowed_origins)
