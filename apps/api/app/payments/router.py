import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.auth.dependencies import CurrentUser
from app.core.config import Settings, get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.rate_limit import rate_limit
from app.core.responses import success
from app.payments.schemas import RazorpayCheckoutVerification
from app.payments.service import RazorpayGateway, verify_checkout_signature, verify_webhook_signature
from app.restaurants.repository import RestaurantRepository

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger(__name__)


@router.post("/razorpay/verify")
async def verify_razorpay_checkout(
    payload: RazorpayCheckoutVerification,
    request: Request,
    user: CurrentUser,
    database: DatabaseDependency,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if (
        not settings.razorpay_key_id
        or not settings.razorpay_key_secret
        or not settings.razorpay_mode.strip()
    ):
        raise ApiError(
            503, "PAYMENT_UNAVAILABLE", "Razorpay checkout verification is not configured"
        )
    if not verify_checkout_signature(
        payload.order_id, payload.payment_id, payload.signature, settings.razorpay_key_secret
    ):
        logger.warning("Razorpay checkout verification rejected: INVALID_CHECKOUT_SIGNATURE")
        raise ApiError(400, "INVALID_PAYMENT_SIGNATURE", "Payment signature could not be verified")
    if not await database.user_owns_payment_order(payload.order_id, user.id):
        raise ApiError(404, "PAYMENT_NOT_FOUND", "Payment order was not found")

    provider_payment = await RazorpayGateway(
        request.app.state.http_client, settings
    ).fetch_payment(payload.payment_id)
    if provider_payment["order_id"] != payload.order_id:
        raise ApiError(400, "PAYMENT_ORDER_MISMATCH", "Payment could not be matched to this order")

    captured = provider_payment["status"] == "captured"
    if provider_payment["status"] not in {"captured", "failed", "authorized", "created"}:
        raise ApiError(502, "PAYMENT_PROVIDER_ERROR", "Razorpay returned an unsupported payment status")
    if captured:
        amount_paise = provider_payment["amount"]
        currency = provider_payment["currency"]
        processed = await database.process_payment_webhook(
            payload.order_id, payload.payment_id, amount_paise, currency, True
        )
        if not processed and hasattr(database, "process_hotel_payment_webhook"):
            processed = await database.process_hotel_payment_webhook(
                payload.order_id, payload.payment_id, amount_paise, currency, True
            )
        if not processed:
            processed = await RestaurantRepository(database.pool).process_payment_webhook(
                payload.order_id, payload.payment_id, amount_paise, currency, True
            )
        if not processed:
            raise ApiError(404, "PAYMENT_NOT_FOUND", "Payment order was not found")
    return success(
        {"verified": captured, "status": "captured" if captured else provider_payment["status"]},
        "Payment verified" if captured else "Payment is not captured yet",
    )


@router.post("/razorpay/webhook")
async def razorpay_webhook(
    request: Request,
    database: DatabaseDependency,
    settings: Settings = Depends(get_settings),
    _limit: None = Depends(rate_limit("razorpay-webhook", 300, 300)),
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
