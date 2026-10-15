import hashlib
import hmac
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx

from app.core.config import Settings
from app.core.errors import ApiError


class RazorpayGateway:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def create_order(self, booking_id: UUID, amount_inr: Decimal) -> dict[str, Any]:
        if not self.settings.razorpay_key_id or not self.settings.razorpay_key_secret:
            raise ApiError(503, "PAYMENT_UNAVAILABLE", "Razorpay is not configured")
        self._require_matching_mode()
        amount_paise = int(amount_inr * 100)
        try:
            response = await self.client.post(
                "https://api.razorpay.com/v1/orders",
                auth=(self.settings.razorpay_key_id, self.settings.razorpay_key_secret),
                json={"amount": amount_paise, "currency": "INR", "receipt": str(booking_id)},
            )
        except httpx.RequestError as exc:
            raise ApiError(503, "PAYMENT_UNAVAILABLE", "Razorpay could not be reached") from exc
        if response.is_error:
            raise ApiError(502, "PAYMENT_PROVIDER_ERROR", "Razorpay could not create an order")
        try:
            order = response.json()
            order_id = order["id"]
            if (
                not isinstance(order_id, str)
                or not order_id
                or order["amount"] != amount_paise
                or order["currency"] != "INR"
            ):
                raise ValueError("Razorpay order amount mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(502, "PAYMENT_PROVIDER_ERROR", "Razorpay returned an invalid order") from exc
        return {
            "order_id": order_id,
            "amount_paise": amount_paise,
            "currency": "INR",
            "key_id": self.settings.razorpay_key_id,
        }

    def _require_matching_mode(self) -> None:
        mode = self.settings.razorpay_mode.strip().lower()
        expected_prefix = {"test": "rzp_test_", "live": "rzp_live_"}.get(mode)
        if expected_prefix is None or not self.settings.razorpay_key_id.startswith(expected_prefix):
            raise ApiError(503, "PAYMENT_MODE_UNCONFIGURED", "Razorpay mode and key are not configured consistently")

    async def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        if not self.settings.razorpay_key_id or not self.settings.razorpay_key_secret:
            raise ApiError(503, "PAYMENT_UNAVAILABLE", "Razorpay is not configured")
        self._require_matching_mode()
        try:
            response = await self.client.get(
                f"https://api.razorpay.com/v1/payments/{payment_id}",
                auth=(self.settings.razorpay_key_id, self.settings.razorpay_key_secret),
            )
        except httpx.RequestError as exc:
            raise ApiError(503, "PAYMENT_UNAVAILABLE", "Razorpay could not be reached") from exc
        if response.is_error:
            raise ApiError(502, "PAYMENT_PROVIDER_ERROR", "Razorpay could not verify this payment")
        try:
            payment = response.json()
            if (
                payment["id"] != payment_id
                or not isinstance(payment["order_id"], str)
                or not isinstance(payment["amount"], int)
                or isinstance(payment["amount"], bool)
                or payment["amount"] <= 0
                or not isinstance(payment["currency"], str)
                or not isinstance(payment["status"], str)
            ):
                raise ValueError("invalid payment fields")
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(502, "PAYMENT_PROVIDER_ERROR", "Razorpay returned an invalid payment") from exc
        return payment


def verify_webhook_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_checkout_signature(
    order_id: str, payment_id: str, signature: str | None, secret: str
) -> bool:
    if not order_id or not payment_id or not signature or not secret:
        return False
    expected = hmac.new(
        secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
