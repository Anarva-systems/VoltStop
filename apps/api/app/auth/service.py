from uuid import UUID

import httpx

from app.core.config import Settings
from app.core.errors import ApiError
from app.core.models import AuthenticatedUser


async def verify_supabase_access_token(
    access_token: str,
    client: httpx.AsyncClient,
    settings: Settings,
) -> AuthenticatedUser:
    if not settings.supabase_url or not settings.supabase_api_key:
        raise ApiError(503, "AUTH_UNAVAILABLE", "Supabase authentication is not configured")

    try:
        response = await client.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "apikey": settings.supabase_api_key,
                "Authorization": f"Bearer {access_token}",
            },
        )
    except httpx.TimeoutException as exc:
        raise ApiError(503, "AUTH_UNAVAILABLE", "Supabase authentication timed out") from exc
    except httpx.RequestError as exc:
        raise ApiError(503, "AUTH_UNAVAILABLE", "Supabase authentication is unavailable") from exc

    if response.status_code in (401, 403):
        raise ApiError(401, "UNAUTHENTICATED", "Access token is invalid or expired")
    if response.is_error:
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
