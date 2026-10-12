from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str | None = None
    phone: str | None = None
    user_metadata: dict[str, Any] | None = None
    app_metadata: dict[str, Any] | None = None
