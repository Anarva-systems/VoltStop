import logging
from uuid import UUID
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.models import AuthenticatedUser

logger = logging.getLogger(__name__)


async def verify_supabase_access_token(
    access_token: str,
    client: httpx.AsyncClient,
    settings: Settings,
) -> AuthenticatedUser:
    if not settings.supabase_url or not settings.supabase_api_key:
        logger.error(
            "Supabase Auth verification is not configured url_configured=%s api_key_configured=%s",
            bool(settings.supabase_url),
            bool(settings.supabase_api_key),
        )
        raise ApiError(503, "AUTH_UNAVAILABLE", "Supabase authentication is not configured")

    supabase_host = urlsplit(settings.supabase_url).hostname or "invalid-host"
    try:
        response = await client.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.supabase_api_key,
                "Authorization": f"Bearer {access_token}",
            },
        )
    except httpx.TimeoutException as exc:
        logger.warning("Supabase Auth user lookup timed out host=%s", supabase_host)
        raise ApiError(503, "AUTH_UNAVAILABLE", "Supabase authentication timed out") from exc
    except httpx.RequestError as exc:
        # Do not log the request or exception text: it can contain request data.
        # The exception class distinguishes DNS, TLS, connect, and protocol failures.
        logger.warning(
            "Supabase Auth user lookup transport failure host=%s error_type=%s",
            supabase_host,
            type(exc).__name__,
        )
        raise ApiError(503, "AUTH_UNAVAILABLE", "Supabase authentication is unavailable") from exc

    if response.status_code in (401, 403):
        logger.info("Supabase Auth rejected an access token host=%s status=%s", supabase_host, response.status_code)
        raise ApiError(401, "UNAUTHENTICATED", "Access token is invalid or expired")
    if response.is_error:
        logger.warning("Supabase Auth returned an error host=%s status=%s", supabase_host, response.status_code)
        raise ApiError(502, "AUTH_PROVIDER_ERROR", "Supabase could not validate the access token")

    try:
        payload = response.json()
        user_id = UUID(payload["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ApiError(502, "AUTH_PROVIDER_ERROR", "Supabase returned an invalid user response") from exc

    return AuthenticatedUser(
        id=user_id,
        email=payload.get("email"),
        phone=payload.get("phone"),
        user_metadata=payload.get("user_metadata") or {},
        app_metadata=payload.get("app_metadata") or {},
    )
