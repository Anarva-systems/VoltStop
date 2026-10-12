from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser
from app.auth.service import verify_supabase_access_token
from app.core.config import Settings, get_settings
from app.core.dependencies import get_http_client
from app.core.responses import success

router = APIRouter(prefix="/auth", tags=["auth"])


class VerifyRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=8192)


def public_user(user: Any) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "phone": user.phone,
        "user_metadata": user.user_metadata,
        "app_metadata": user.app_metadata,
    }


@router.post("/verify")
async def verify_token(
    payload: VerifyRequest,
    client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    user = await verify_supabase_access_token(payload.access_token, client, settings)
    return success(public_user(user), "Access token is valid")


@router.get("/me")
async def get_me(user: CurrentUser) -> dict[str, Any]:
    return success(public_user(user))
