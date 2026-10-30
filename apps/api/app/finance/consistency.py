from decimal import Decimal
from typing import Any


def check_financial_consistency(record: dict[str, Any]) -> list[dict[str, str]]:
    """Return explicit diagnostics; this function never mutates or repairs records."""
    issues: list[dict[str, str]] = []
    booking_status = record.get("booking_status")
    payment_status = record.get("payment_status")
    booking_amount = record.get("booking_amount")
    payment_amount = record.get("payment_amount")
    refund_total = Decimal(str(record.get("reserved_refund_amount") or 0))
    completed_refund_total = Decimal(str(record.get("completed_refund_amount") or 0))
    payout = record.get("vendor_payout")
    eligible_revenue = record.get("eligible_revenue")
    entity = str(record.get("booking_id") or record.get("payment_id") or "unknown")

    if payment_amount is None and booking_status in ("confirmed", "completed"):
        issues.append({"code": "CONFIRMED_BOOKING_WITHOUT_PAYMENT", "entity_id": entity,
                       "message": "A confirmed or completed booking has no linked payment."})
    elif booking_status in ("confirmed", "completed") and (payment_status != "captured" or not record.get("webhook_verified")):
        issues.append({"code": "CONFIRMED_BOOKING_PAYMENT_INVALID", "entity_id": entity,
                       "message": "A confirmed or completed booking lacks a captured, verified payment."})
    if booking_amount is not None and payment_amount is not None and booking_status in ("confirmed", "completed"):
        if Decimal(str(booking_amount)) != Decimal(str(payment_amount)):
            issues.append({"code": "BOOKING_PAYMENT_AMOUNT_MISMATCH", "entity_id": entity,
                           "message": "Booking and payment amounts do not match."})
    if payment_amount is None and refund_total > 0:
        issues.append({"code": "REFUND_WITHOUT_PAYMENT", "entity_id": entity,
                       "message": "A refund is recorded without a linked payment."})
    elif payment_amount is not None and refund_total > Decimal(str(payment_amount)):
        issues.append({"code": "REFUNDS_EXCEED_PAYMENT", "entity_id": entity,
                       "message": "Refunds reserved or completed exceed the captured payment."})
    if payment_amount is not None and payment_status == "refunded" and completed_refund_total != Decimal(str(payment_amount)):
        issues.append({"code": "REFUNDED_PAYMENT_TOTAL_MISMATCH", "entity_id": entity,
                       "message": "Payment is marked refunded, but completed refunds do not equal the captured amount."})
    if payout is not None and eligible_revenue is not None and Decimal(str(payout)) > Decimal(str(eligible_revenue)):
        issues.append({"code": "PAYOUT_EXCEEDS_ELIGIBLE_REVENUE", "entity_id": entity,
                       "message": "Vendor payout exceeds eligible captured revenue."})
    return issues


TRANSFER_STATUSES_WITH_PROVIDER_PROOF = {"processed", "settled", "reversed", "failed"}


def check_payout_consistency(record: dict[str, Any]) -> list[dict[str, str]]:
    """Findings for one payout ledger row joined against the order that carried it."""
    issues: list[dict[str, str]] = []
    payout_id = str(record.get("id") or record.get("razorpay_order_id") or "unknown")
    order_amount = record.get("order_amount_inr")
    gross = Decimal(str(record.get("gross_amount_inr") or 0))
    vendor_share = Decimal(str(record.get("vendor_amount_inr") or 0))
    commission = Decimal(str(record.get("commission_inr") or 0))
    status = record.get("payout_status")

    if order_amount is None:
        issues.append({"code": "PAYOUT_ORDER_NOT_FOUND", "entity_id": payout_id,
                       "message": "A payout row references an order that no payment record carries."})
    elif Decimal(str(order_amount)) != gross:
        issues.append({"code": "PAYOUT_GROSS_MISMATCH", "entity_id": payout_id,
                       "message": "Payout gross amount does not match the payment order amount."})
    if vendor_share + commission != gross:
        issues.append({"code": "PAYOUT_SPLIT_MISMATCH", "entity_id": payout_id,
                       "message": "Vendor share and commission do not add up to the gross amount."})
    if status in TRANSFER_STATUSES_WITH_PROVIDER_PROOF and not record.get("razorpay_transfer_id"):
        issues.append({"code": "PAYOUT_TRANSFER_UNMATCHED", "entity_id": payout_id,
                       "message": "Payout status claims a provider outcome without a transfer identifier."})
    return issues
