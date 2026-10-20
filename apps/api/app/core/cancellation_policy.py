"""Versioned customer cancellation policy used for quotes and settlement requests."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

POLICY_VERSION = "2026-10-20-v1"
MONEY = Decimal("0.01")


def cancellation_quote(amount: Decimal, service_start: datetime, *, now: datetime | None = None) -> dict[str, Any]:
    """Return a stable quote from captured gross amount and time until service start."""
    instant = now or datetime.now(timezone.utc)
    if service_start.tzinfo is None:
        service_start = service_start.replace(tzinfo=timezone.utc)
    hours_before = Decimal(str((service_start - instant).total_seconds())) / Decimal("3600")
    if hours_before >= 48:
        refund_rate, tier = Decimal("1.00"), "48_hours_or_more"
    elif hours_before >= 24:
        refund_rate, tier = Decimal("0.90"), "24_to_48_hours"
    elif hours_before > 0:
        refund_rate, tier = Decimal("0.50"), "under_24_hours"
    else:
        refund_rate, tier = Decimal("0.00"), "service_started"
    gross = Decimal(amount).quantize(MONEY, rounding=ROUND_HALF_UP)
    refund = (gross * refund_rate).quantize(MONEY, rounding=ROUND_HALF_UP)
    return {
        "policy_version": POLICY_VERSION,
        "tier": tier,
        "hours_before_start": max(hours_before, Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "captured_amount_inr": gross,
        "customer_refund_inr": refund,
        "retained_amount_inr": gross - refund,
        "refund_percent": int(refund_rate * 100),
        "gateway_fee_deduction_inr": Decimal("0.00"),
    }
