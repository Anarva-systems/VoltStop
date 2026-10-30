"""How a captured rupee is shared between VoltStop and a vendor.

These functions only decide numbers. Nothing here moves money: the split becomes
a transfer instruction inside an Razorpay order, and the provider reports back
through signed webhooks that a separate repository records.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN
from typing import Any

LINKED_ACCOUNT_PATTERN = re.compile(r"^acc_[A-Za-z0-9]+$")

# Mask formats are shared by the admin review form and the vendor self-submission
# form so neither can drift from the database checks that reject a full number.
KYC_PAN_MASK = r"^[A-Z]{5}\*{4}[A-Z0-9]$"
KYC_BANK_ACCOUNT_MASK = r"^\*{4,13}[0-9]{4}$"
KYC_GSTIN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$"

MAX_PAYOUT_RATE_BPS = 5000
# Razorpay charges its fee to the platform wallet, so a split that leaves the
# platform with less than this cannot settle and is refused instead of attempted.
MINIMUM_PLATFORM_RETENTION_BPS = 300

_KYC_PASSED = "verified"
_ONBOARDING_APPROVED = "approved"


class MoneyUnavailable(ValueError):
    """Raised when a payout plan cannot be built from the supplied profile."""


@dataclass(frozen=True)
class PayoutSplit:
    payout_id: str
    vendor_id: str
    linked_account_id: str
    source_kind: str
    source_reference_id: str
    rate_bps: int
    gross_amount_inr: Decimal
    vendor_amount_inr: Decimal
    commission_inr: Decimal

    @property
    def vendor_amount_paise(self) -> int:
        return _inr_to_paise(self.vendor_amount_inr)

    def transfer(self) -> dict[str, Any]:
        """The transfer object Razorpay applies once the payment is captured."""
        return {
            "account_id": self.linked_account_id,
            "amount": self.vendor_amount_paise,
            "currency": "INR",
            "notes": {"voltstop_payout_id": self.payout_id},
            "options": {"utr": True},
        }

    def ledger_values(self) -> dict[str, Any]:
        return {
            "id": self.payout_id,
            "vendor_id": self.vendor_id,
            "source_kind": self.source_kind,
            "source_reference_id": self.source_reference_id,
            "rate_bps": self.rate_bps,
            "gross_amount_inr": self.gross_amount_inr,
            "vendor_amount_inr": self.vendor_amount_inr,
            "commission_inr": self.commission_inr,
        }


def effective_rate_bps(vendor: dict[str, Any], platform_rate_bps: int) -> int:
    override = vendor.get("commission_rate_bps_override")
    rate = platform_rate_bps if override is None else int(override)
    if not 0 <= rate <= MAX_PAYOUT_RATE_BPS:
        raise MoneyUnavailable(
            f"Commission rate {rate} bps is outside the 0-{MAX_PAYOUT_RATE_BPS} bps payout range"
        )
    return rate


def unroutable_reason(vendor: dict[str, Any] | None) -> str | None:
    """Why this vendor's payments stay in the platform wallet, or None if routable."""
    if vendor is None:
        return "vendor_profile_missing"
    if not vendor.get("payouts_enabled"):
        return "payouts_disabled"
    account_id = vendor.get("razorpay_linked_account_id")
    if not account_id or not LINKED_ACCOUNT_PATTERN.match(str(account_id)):
        return "linked_account_missing"
    if vendor.get("kyc_status") != _KYC_PASSED:
        return "kyc_not_verified"
    if vendor.get("onboarding_status") != _ONBOARDING_APPROVED:
        return "onboarding_not_approved"
    override = vendor.get("commission_rate_bps_override")
    if override is not None and not 0 <= int(override) <= MAX_PAYOUT_RATE_BPS:
        return "commission_rate_invalid"
    if override is not None and int(override) < MINIMUM_PLATFORM_RETENTION_BPS:
        return "platform_retention_below_floor"
    return None


_ROUTING_STATE_BY_REASON = {
    "payouts_disabled": "disabled",
    "linked_account_missing": "account_required",
    "kyc_not_verified": "kyc_required",
    "onboarding_not_approved": "approval_required",
    "commission_rate_invalid": "rate_invalid",
    "platform_retention_below_floor": "rate_invalid",
    "vendor_profile_missing": "profile_required",
}


def payout_status_view(profile: dict[str, Any], *, settlement_enabled: bool) -> dict[str, Any]:
    """Routing state for one vendor, safe to show that vendor in their own portal."""
    reason = unroutable_reason(profile)
    override = profile.get("commission_rate_bps_override")
    platform_rate = profile.get("platform_rate_bps")
    if override is not None:
        rate, rate_source = int(override), "vendor_override"
    elif platform_rate is not None:
        rate, rate_source = int(platform_rate), "platform_policy"
    else:
        rate, rate_source = None, None
    if reason is not None:
        state = _ROUTING_STATE_BY_REASON.get(reason, "blocked")
    elif not settlement_enabled:
        state = "ready_disabled"
    else:
        state = "routing_enabled"
    return {
        "state": state,
        "blocked_reason": reason,
        "payouts_enabled": bool(profile.get("payouts_enabled")),
        "settlement_enabled": bool(settlement_enabled),
        "linked_account_id": profile.get("razorpay_linked_account_id"),
        "kyc_status": profile.get("kyc_status"),
        "onboarding_status": profile.get("onboarding_status"),
        "commission_rate_bps": rate,
        "commission_rate_source": rate_source,
        "retention_floor_bps": MINIMUM_PLATFORM_RETENTION_BPS,
        "kyc": {
            "status": profile.get("kyc_status"),
            "reference": profile.get("kyc_reference"),
            "gstin": profile.get("kyc_gstin"),
            "pan_masked": profile.get("kyc_pan_masked"),
            "bank_account_masked": profile.get("bank_account_masked"),
            "verified_at": profile.get("kyc_verified_at"),
        },
        "routed_inr": profile.get("routed_inr"),
        "planned_inr": profile.get("planned_inr"),
        "failed_transfers": profile.get("failed_transfers"),
        "last_transfer_at": profile.get("last_transfer_at"),
    }


def plan_payout(
    *,
    payout_id: str,
    vendor: dict[str, Any],
    vendor_id: Any,
    source_kind: str,
    source_reference_id: Any,
    gross_amount_inr: Decimal,
    platform_rate_bps: int,
) -> PayoutSplit | None:
    """Build a transfer instruction, or None when this payment must not be routed."""
    if unroutable_reason(vendor) is not None:
        return None
    gross_amount_inr = _rupees(gross_amount_inr)
    if gross_amount_inr <= 0:
        return None
    rate_bps = effective_rate_bps(vendor, platform_rate_bps)
    if rate_bps < MINIMUM_PLATFORM_RETENTION_BPS:
        return None

    gross_paise = _inr_to_paise(gross_amount_inr, rounding=ROUND_DOWN)
    commission_paise = gross_paise * rate_bps // 10000
    vendor_paise = gross_paise - commission_paise
    if vendor_paise <= 0 or commission_paise <= 0:
        return None

    return PayoutSplit(
        payout_id=str(payout_id),
        vendor_id=str(vendor_id),
        linked_account_id=str(vendor["razorpay_linked_account_id"]),
        source_kind=source_kind,
        source_reference_id=str(source_reference_id),
        rate_bps=rate_bps,
        gross_amount_inr=gross_amount_inr,
        vendor_amount_inr=_paise_to_inr(vendor_paise),
        commission_inr=_paise_to_inr(commission_paise),
    )


def _rupees(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _inr_to_paise(value: Decimal, *, rounding: str = ROUND_HALF_UP) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=rounding))


def _paise_to_inr(value: int) -> Decimal:
    return (Decimal(value) / Decimal(100)).quantize(Decimal("0.01"))
