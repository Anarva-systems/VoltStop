from decimal import Decimal

from app.core.errors import ApiError


def validate_refund_amount(captured: Decimal, reserved: Decimal, requested: Decimal | None = None) -> tuple[Decimal, Decimal]:
    remaining = max(captured - reserved, Decimal("0"))
    value = requested if requested is not None else remaining
    if value <= 0:
        raise ApiError(409, "REFUND_NOT_ELIGIBLE", "No refundable balance remains")
    if value > remaining:
        raise ApiError(409, "REFUND_AMOUNT_EXCEEDS_CAPTURE", "Refund amount exceeds the remaining captured amount")
    return value, remaining - value
