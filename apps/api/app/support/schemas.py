from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["account", "booking", "payment", "technical", "business", "other"]
    subject: str = Field(min_length=4, max_length=160)
    message: str = Field(min_length=8, max_length=4000)
    booking_id: UUID | None = None


class TicketMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=2, max_length=4000)


class TicketAdminPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["open", "in_progress", "waiting_on_customer", "resolved", "closed"] | None = None
    priority: Literal["normal", "high", "urgent"] | None = None
    assigned_to: UUID | None = None
    reason: str = Field(min_length=8, max_length=1000)
