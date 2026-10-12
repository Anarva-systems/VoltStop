import hashlib
import hmac
from decimal import Decimal
from uuid import UUID
from typing import Any

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
            if order["amount"] != amount_paise or order["currency"] != "INR":
                raise ValueError("Razorpay order amount mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            raise ApiError(502, "PAYMENT_PROVIDER_ERROR", "Razorpay returned an invalid order") from exc
        return {
                    "order_id": order_id,
                    "amount_paise": amount_paise,
                    "currency": "INR",
                    "key_id": self.settings.razorpay_key_id,
                }


def verify_webhook_signature(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
