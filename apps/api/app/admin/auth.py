from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends

from app.auth.dependencies import CurrentUser
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.config import get_settings
from app.admin.repository import AdminRepository


@dataclass(frozen=True)
class AdminContext:
    user_id: UUID
    email: str | None
    role_name: str
    permissions: frozenset[str]


async def require_admin(user: CurrentUser, database: DatabaseDependency) -> AdminContext:
    repository = AdminRepository(database.pool)
    identity = await repository.identity(user.id)
    bootstrap_email = get_settings().bootstrap_admin_email.strip().lower()
    if identity is None and user.email and bootstrap_email and user.email.strip().lower() == bootstrap_email:
        admin_count = await database.pool.fetchval("select count(*) from public.admin_users")
        if admin_count == 0:
            await database.pool.execute(
                """insert into public.admin_users (user_id, role_name, is_active)
                   values ($1, 'SUPER_ADMIN', true)
                   on conflict (user_id) do update set role_name='SUPER_ADMIN', is_active=true, updated_at=now()""",
                user.id,
            )
            identity = await repository.identity(user.id)
    if identity is None or not identity["is_active"]:
        raise ApiError(403, "ADMIN_ACCESS_REQUIRED", "This account is not authorized for the admin platform")
    return AdminContext(
        user_id=user.id,
        email=user.email,
        role_name=identity["role_name"],
        permissions=frozenset(identity["permissions"]),
    )


def require_permission(permission: str):
    async def check(admin: Annotated[AdminContext, Depends(require_admin)]) -> AdminContext:
        if permission not in admin.permissions:
            raise ApiError(403, "ADMIN_PERMISSION_REQUIRED", "Your administrator role does not allow this action")
        return admin
    return check


AdminUser = Annotated[AdminContext, Depends(require_admin)]
