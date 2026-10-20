from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.cancellation_policy import cancellation_quote


@pytest.mark.parametrize(
    ("hours_before", "refund", "retained", "tier"),
    [
        (49, "100.00", "0.00", "48_hours_or_more"),
        (48, "100.00", "0.00", "48_hours_or_more"),
        (24, "90.00", "10.00", "24_to_48_hours"),
        (1, "50.00", "50.00", "under_24_hours"),
        (0, "0.00", "100.00", "service_started"),
    ],
)
def test_cancellation_policy_boundaries(hours_before, refund, retained, tier):
    now = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    quote = cancellation_quote(
        Decimal("100.00"), now + timedelta(hours=hours_before), now=now
    )

    assert quote["customer_refund_inr"] == Decimal(refund)
    assert quote["retained_amount_inr"] == Decimal(retained)
    assert quote["tier"] == tier
    assert quote["gateway_fee_deduction_inr"] == Decimal("0.00")
