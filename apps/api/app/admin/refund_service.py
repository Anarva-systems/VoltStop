from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx

from app.admin.repository import AdminRepository
from app.core.config import Settings
from app.core.errors import ApiError


class RefundService:
    """The only application service that may ask Razorpay to issue a refund."""

    def __init__(self, repository: AdminRepository, client: httpx.AsyncClient, settings: Settings):
        self.repository = repository
        self.client = client
        self.settings = settings

    async def issue(self, actor_id: UUID, refund_id: UUID, reason: str, role: str,
                    metadata: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        if not self.settings.razorpay_key_id or not self.settings.razorpay_key_secret:
            raise ApiError(503, "REFUND_PROVIDER_UNAVAILABLE", "Razorpay refund credentials are not configured")

        refund, claimed = await self.repository.claim_refund_for_processing(actor_id, role, refund_id, metadata)
        if not claimed:
            # Only a single caller can atomically claim an approved request.
            # Existing processing results require webhook reconciliation.
            return refund, False

        try:
            response = await self.client.post(
                f"https://api.razorpay.com/v1/payments/{refund['razorpay_payment_id']}/refund",
                auth=(self.settings.razorpay_key_id, self.settings.razorpay_key_secret),
                json={
                    "amount": int(Decimal(refund["amount_inr"]) * 100),
                    "notes": {"voltstop_refund_id": str(refund["id"]), "reason": reason[:250]},
                },
            )
        except httpx.RequestError as exc:
            # Timeout is ambiguous: the provider may have accepted the request.
            # Keep it processing and require reconciliation; never retry blindly.
            await self.repository.finish_refund(
                refund["id"], None, "response_unknown", "processing", actor_id, role, metadata,
                "Provider response was not received; reconcile before retrying.",
            )
            raise ApiError(503, "REFUND_RECONCILIATION_REQUIRED",
                           "Provider response is unknown. The refund is held for reconciliation.") from exc

        if response.is_error:
            # A provider rejection response confirms that the refund was not
            # accepted. Transport/server errors remain ambiguous and are held.
            if response.status_code >= 500:
                await self.repository.finish_refund(
                    refund["id"], None, "response_unknown", "processing", actor_id, role, metadata,
                    f"Provider returned HTTP {response.status_code}; reconcile before retrying.",
                )
                raise ApiError(503, "REFUND_RECONCILIATION_REQUIRED",
                               "Provider response is unknown. The refund is held for reconciliation.")
            await self.repository.finish_refund(
                refund["id"], None, "rejected", "failed", actor_id, role, metadata,
                f"Provider rejected the refund (HTTP {response.status_code})."
            )
            raise ApiError(502, "REFUND_PROVIDER_REJECTED", "Razorpay rejected the refund request")

        try:
            provider = response.json()
            if provider["payment_id"] != refund["razorpay_payment_id"]:
                raise ValueError("Payment ID mismatch")
            if int(provider["amount"]) != int(Decimal(refund["amount_inr"]) * 100):
                raise ValueError("Refund amount mismatch")
            provider_id = str(provider["id"])
            provider_status = str(provider.get("status", "pending"))
        except (ValueError, KeyError, TypeError) as exc:
            await self.repository.finish_refund(
                refund["id"], None, "response_invalid", "processing", actor_id, role, metadata,
                "Provider response could not be validated; reconcile before retrying.",
            )
            raise ApiError(503, "REFUND_RECONCILIATION_REQUIRED",
                           "Provider response could not be verified. The refund is held for reconciliation.") from exc

        local_status = "completed" if provider_status == "processed" else "failed" if provider_status == "failed" else "processing"
        updated = await self.repository.finish_refund(refund["id"], provider_id, provider_status, local_status,
                                                      actor_id, role, metadata)
        return updated, True
