from typing import Any

from fastapi import APIRouter

from app.auth.dependencies import CurrentUser

from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success
from app.profile import ProfilePatch

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
async def get_profile(user: CurrentUser, database: DatabaseDependency) -> dict[str, Any]:
    profile = await database.profile(user.id)
    if profile is None:
        raise ApiError(404, "PROFILE_NOT_FOUND", "Profile was not found")
    return success(profile)


@router.patch("")
async def patch_profile(
    payload: ProfilePatch,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    changes = payload.changes()
    if not changes:
        raise ApiError(422, "EMPTY_PATCH", "At least one profile field must be provided")
    profile = await database.patch_profile(user.id, changes)
    if profile is None:
        raise ApiError(404, "PROFILE_NOT_FOUND", "Profile was not found")
    return success(profile, "Profile updated")
