import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings, get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success
from app.payments.service import verify_webhook_signature
from app.restaurants.repository import RestaurantRepository

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger(__name__)


@router.post("/razorpay/webhook")
async def razorpay_webhook(
    request: Request,
    database: DatabaseDependency,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")
    if not verify_webhook_signature(raw_body, signature, settings.razorpay_webhook_secret):
        logger.warning("Razorpay webhook rejected: INVALID_WEBHOOK_SIGNATURE")
        raise ApiError(401, "INVALID_WEBHOOK_SIGNATURE", "Webhook signature is invalid")
    try:
        payload = json.loads(raw_body)
        event = payload["event"]
        if event in ("refund.created", "refund.processed", "refund.failed"):
            entity = payload["payload"]["refund"]["entity"]
            refund_id = entity["id"]
            payment_id = entity["payment_id"]
            amount_paise = entity["amount"]
            currency = entity["currency"]
            if (not isinstance(refund_id, str) or not refund_id
                    or not isinstance(payment_id, str) or not payment_id
                    or not isinstance(amount_paise, int) or isinstance(amount_paise, bool) or amount_paise <= 0
                    or not isinstance(currency, str) or not currency):
                raise ValueError("invalid refund fields")
            notes = entity.get("notes")
            try:
                processed = await database.process_refund_webhook(
                    refund_id, payment_id, amount_paise, currency, entity["status"],
                    notes.get("voltstop_refund_id") if isinstance(notes, dict) else None,
                )
                if not processed and hasattr(database, "process_hotel_refund_webhook"):
                    processed = await database.process_hotel_refund_webhook(
                        refund_id, payment_id, amount_paise, currency, entity["status"],
                        notes.get("voltstop_refund_id") if isinstance(notes, dict) else None,
                    )
            except ApiError as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                logger.warning("Razorpay refund webhook rejected: %s", detail.get("code", "REFUND_WEBHOOK_REJECTED"))
                raise
            if not processed:
                raise ApiError(404, "REFUND_NOT_FOUND", "Refund record was not found")
            return success({"received": True, "processed": True}, "Refund event processed")
        entity = payload["payload"]["payment"]["entity"]
        if event not in ("payment.captured", "payment.failed"):
            return success({"received": True, "processed": False}, "Event acknowledged")
        order_id = entity["order_id"]
        payment_id = entity["id"]
        amount_paise = entity["amount"]
        currency = entity["currency"]
        if (not isinstance(order_id, str) or not order_id
                or not isinstance(payment_id, str) or not payment_id
                or not isinstance(amount_paise, int) or isinstance(amount_paise, bool) or amount_paise <= 0
                or not isinstance(currency, str) or not currency):
            raise ValueError("invalid payment fields")
    except (ValueError, KeyError, TypeError) as exc:
        raise ApiError(400, "INVALID_WEBHOOK_PAYLOAD", "Webhook payload is invalid") from exc

    try:
        processed = await database.process_payment_webhook(
            order_id, payment_id, amount_paise, currency, event == "payment.captured"
        )
        if not processed and hasattr(database, "process_hotel_payment_webhook"):
            processed = await database.process_hotel_payment_webhook(
                order_id, payment_id, amount_paise, currency, event == "payment.captured"
            )
        if not processed:
            processed = await RestaurantRepository(database.pool).process_payment_webhook(
                order_id, payment_id, amount_paise, currency, event == "payment.captured"
            )
    except ApiError as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        logger.warning("Razorpay payment webhook rejected: %s", detail.get("code", "PAYMENT_WEBHOOK_REJECTED"))
        raise
    if not processed:
        raise ApiError(404, "PAYMENT_NOT_FOUND", "Payment order was not found")
    return success({"received": True, "processed": True}, "Payment event processed")
