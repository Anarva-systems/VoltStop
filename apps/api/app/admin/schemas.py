from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.payouts.service import KYC_BANK_ACCOUNT_MASK, KYC_GSTIN, KYC_PAN_MASK, MINIMUM_PLATFORM_RETENTION_BPS


class VendorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["approve", "request_changes", "reject", "suspend", "reactivate", "review"]
    reason: str = Field(min_length=8, max_length=1000)


class VendorPayoutRoutingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    razorpay_linked_account_id: str | None = Field(default=None, pattern=r"^acc_[A-Za-z0-9]{6,60}$")
    payouts_enabled: bool = False
    # A rate below the retention floor never routes (plan_payout refuses it), so the
    # form rejects it instead of letting an operator enable a silent dead end.
    commission_rate_bps_override: int | None = Field(
        default=None, ge=MINIMUM_PLATFORM_RETENTION_BPS, le=5000
    )
    reason: str = Field(min_length=8, max_length=1000)


class VendorKycReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["not_started", "submitted", "under_review", "verified", "rejected"]
    kyc_reference: str | None = Field(default=None, min_length=4, max_length=120)
    kyc_gstin: str | None = Field(default=None, pattern=KYC_GSTIN)
    kyc_pan_masked: str | None = Field(default=None, pattern=KYC_PAN_MASK)
    bank_account_masked: str | None = Field(default=None, pattern=KYC_BANK_ACCOUNT_MASK)
    reason: str | None = Field(default=None, min_length=8, max_length=1000)


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
