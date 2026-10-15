from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.service import AuthenticatedUser, verify_supabase_access_token
from app.core.config import get_settings
from app.core.dependencies import get_http_client
from app.core.errors import ApiError

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiError(401, "UNAUTHENTICATED", "A valid bearer token is required")
    user = await verify_supabase_access_token(
        credentials.credentials,
        await get_http_client(request),
        get_settings(),
    )
    pool = getattr(request.app.state, "db_pool", None)
    if pool is not None:
        metadata = user.user_metadata or {}
        display_name = metadata.get("name") or metadata.get("full_name")
        try:
            await pool.execute(
                """
                insert into public.profiles (id, phone, name)
                values ($1, $2, $3)
                on conflict (id) do update set
                  phone = coalesce(excluded.phone, public.profiles.phone),
                  name = coalesce(nullif(excluded.name, ''), public.profiles.name)
                where (excluded.phone is not null
                       and public.profiles.phone is distinct from excluded.phone)
                   or (nullif(excluded.name, '') is not null
                       and public.profiles.name is distinct from nullif(excluded.name, ''))
                """,
                user.id,
                user.phone,
                display_name,
            )
        except Exception as exc:
            raise ApiError(503, "DATABASE_UNAVAILABLE", "User profile could not be synchronized") from exc
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
