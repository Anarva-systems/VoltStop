from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SlotLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: UUID


class CreateBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: UUID
    lock_token: str = Field(min_length=24, max_length=128)
