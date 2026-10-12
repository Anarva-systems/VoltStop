from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx

from app.core.config import Settings
from app.core.errors import ApiError
from app.hotels.repository import HotelRepository


class HotelRefundService:
    """Finance-reviewed hotel refunds with conservative handling of ambiguous provider results."""

    def __init__(self, repository: HotelRepository, client: httpx.AsyncClient, settings: Settings):
        self.repository = repository
        self.client = client
        self.settings = settings

    async def issue(self, refund_id: UUID) -> tuple[dict[str, Any], bool]:
        if not self.settings.razorpay_key_id or not self.settings.razorpay_key_secret:
            raise ApiError(503,"REFUND_PROVIDER_UNAVAILABLE","Razorpay refund credentials are not configured")
        refund, claimed = await self.repository.claim_refund(refund_id)
        if not claimed:
            return refund,False
        try:
            response = await self.client.post(
                f"https://api.razorpay.com/v1/payments/{refund['razorpay_payment_id']}/refund",
                auth=(self.settings.razorpay_key_id,self.settings.razorpay_key_secret),
                json={"amount":int(Decimal(refund["amount_inr"])*100),
                      "notes":{"voltstop_refund_id":str(refund["id"]),"reason":"hotel reservation cancellation"}},
            )
        except httpx.RequestError as exc:
            await self.repository.finish_refund(refund_id,None,"response_unknown","processing","Provider response unknown; reconcile before retry.")
            raise ApiError(503,"REFUND_RECONCILIATION_REQUIRED","Provider response is unknown; reconciliation is required") from exc
        if response.is_error:
            if response.status_code >= 500:
                await self.repository.finish_refund(refund_id,None,"response_unknown","processing",f"Provider HTTP {response.status_code}; reconcile before retry.")
                raise ApiError(503,"REFUND_RECONCILIATION_REQUIRED","Provider response is unknown; reconciliation is required")
            await self.repository.finish_refund(refund_id,None,"rejected","failed",f"Provider rejected refund (HTTP {response.status_code}).")
            raise ApiError(502,"REFUND_PROVIDER_REJECTED","Razorpay rejected the refund")
        try:
            provider=response.json()
            if provider["payment_id"] != refund["razorpay_payment_id"] or int(provider["amount"]) != int(Decimal(refund["amount_inr"])*100):
                raise ValueError("Refund response mismatch")
            provider_id=str(provider["id"])
            provider_status=str(provider.get("status","pending"))
        except (ValueError,KeyError,TypeError) as exc:
            await self.repository.finish_refund(refund_id,None,"response_invalid","processing","Provider result could not be validated; reconcile before retry.")
            raise ApiError(503,"REFUND_RECONCILIATION_REQUIRED","Provider result could not be verified; reconciliation is required") from exc
        status="completed" if provider_status in ("processed","completed") else "failed" if provider_status=="failed" else "processing"
        return await self.repository.finish_refund(refund_id,provider_id,provider_status,status),True
