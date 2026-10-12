from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID


class CustomerDisputeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_id: UUID
    reason: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=8, max_length=4000)


class DisputeMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=4, max_length=4000)
