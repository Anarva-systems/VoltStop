from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VendorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "request_changes", "reject", "suspend", "reactivate", "review"]
    reason: str = Field(min_length=8, max_length=1000)


class RefundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_id: UUID
    amount_inr: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=8, max_length=1000)


class RefundDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=8, max_length=1000)


class DisputeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_id: UUID
    reason: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=8, max_length=4000)


class DisputeAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["investigate", "await_customer", "await_vendor", "resolve", "reject", "close", "note", "escalate"]
    message: str = Field(min_length=4, max_length=2000)


class DisputeRefundCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_inr: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=8, max_length=1000)


class AdminUserPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_name: Literal["SUPER_ADMIN", "OPERATIONS_ADMIN", "FINANCE_ADMIN", "SUPPORT_ADMIN", "VENDOR_MANAGER"]
    is_active: bool
    reason: str = Field(min_length=8, max_length=1000)
