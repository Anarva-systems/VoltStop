"""Ledger writes for vendor payout transfers.

A row is created only for a split that was actually sent to the provider with an
order, and only a signed webhook may move it past "planned".
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from app.core.errors import ApiError
from app.payouts.service import PayoutSplit, plan_payout, unroutable_reason

TRANSFER_STATUSES = {
    "transfer.processed": "processed",
    "transfer.settled": "settled",
    "transfer.failed": "failed",
    "transfer.reversed": "reversed",
}

_ALLOWED_TRANSITIONS = {
    "planned": {"processed", "settled", "failed", "reversed"},
    "processed": {"settled", "failed", "reversed"},
    "settled": {"reversed"},
    "failed": set(),
    "reversed": set(),
}


class PayoutRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def payout_profile(self, vendor_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(
                """select v.id, v.payouts_enabled, v.razorpay_linked_account_id,
                          v.commission_rate_bps_override,
                          o.status as onboarding_status, o.kyc_status
                   from public.vendors v
                   left join public.vendor_onboarding o on o.vendor_id = v.id
                   where v.id = $1""",
                vendor_id,
            )

    async def platform_rate_bps(self) -> int | None:
        async with self.pool.acquire() as connection:
            return await connection.fetchval(
                "select rate_bps from public.platform_commission_settings where id = 1"
            )

    async def plan_for_payment(
        self,
        *,
        payout_id: UUID,
        vendor_id: UUID,
        source_kind: str,
        source_reference_id: UUID,
        gross_amount_inr: Decimal,
    ) -> PayoutSplit | None:
        profile = await self.payout_profile(vendor_id)
        if profile is None or unroutable_reason(profile) is not None:
            return None
        platform_rate = await self.platform_rate_bps()
        if platform_rate is None:
            raise ApiError(
                503, "PAYOUT_CONFIGURATION_MISSING", "Platform commission rate is not configured"
            )
        return plan_payout(
            payout_id=payout_id,
            vendor=profile,
            vendor_id=vendor_id,
            source_kind=source_kind,
            source_reference_id=source_reference_id,
            gross_amount_inr=gross_amount_inr,
            platform_rate_bps=int(platform_rate),
        )

    async def record_planned_transfer(self, split: PayoutSplit, razorpay_order_id: str) -> bool:
        values = split.ledger_values()
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """insert into public.vendor_payout_transfers(
                     id, vendor_id, source_kind, source_reference_id, razorpay_order_id,
                     currency, gross_amount_inr, vendor_amount_inr, commission_inr, rate_bps, status
                   ) values ($1,$2,$3,$4,$5,'INR',$6,$7,$8,$9,'planned')
                   on conflict (razorpay_order_id, vendor_id) do nothing
                   returning id""",
                UUID(values["id"]),
                UUID(values["vendor_id"]),
                values["source_kind"],
                UUID(values["source_reference_id"]),
                razorpay_order_id,
                values["gross_amount_inr"],
                values["vendor_amount_inr"],
                values["commission_inr"],
                values["rate_bps"],
            )
        return row is not None

    async def apply_transfer_event(
        self,
        *,
        payout_id: UUID,
        event: str,
        transfer_id: str,
        source_payment_id: str,
        amount_paise: int,
        currency: str,
        failure_reason: str | None = None,
        settlement_utr: str | None = None,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Reconcile one signed provider event against the ledger."""
        status = TRANSFER_STATUSES[event]
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """select id, vendor_id, status, razorpay_transfer_id, currency,
                              vendor_amount_inr, gross_amount_inr, rate_bps
                       from public.vendor_payout_transfers where id = $1 for update""",
                    payout_id,
                )
                if current is None:
                    return None
                if current["razorpay_transfer_id"] not in (None, transfer_id):
                    raise ApiError(
                        409, "PAYOUT_TRANSFER_MISMATCH",
                        "This payout record already belongs to another provider transfer",
                    )
                if str(current["currency"]) != currency or int(
                    (Decimal(str(current["vendor_amount_inr"])) * 100).to_integral_value()
                ) != amount_paise:
                    raise ApiError(
                        409, "PAYOUT_AMOUNT_MISMATCH",
                        "Transfer amount does not match the payout ledger",
                    )
                if current["status"] == status:
                    return dict(current)
                if status not in _ALLOWED_TRANSITIONS[current["status"]]:
                    raise ApiError(
                        409, "PAYOUT_STATE_CONFLICT",
                        f"A payout in state {current['status']} cannot become {status}",
                    )
                updated = await connection.fetchrow(
                    """update public.vendor_payout_transfers
                       set status = $2, razorpay_transfer_id = $3, razorpay_payment_id = $4,
                           settlement_utr = coalesce($5, settlement_utr),
                           failure_reason = case when $2 = 'failed'
                             then coalesce($6, 'Transfer reported by the provider as failed')
                             else failure_reason end,
                           provider_event_at = $7
                       where id = $1
                       returning id, vendor_id, status, razorpay_transfer_id, vendor_amount_inr,
                                 commission_inr, gross_amount_inr, rate_bps""",
                    payout_id,
                    status,
                    transfer_id,
                    source_payment_id,
                    settlement_utr,
                    failure_reason,
                    occurred_at or datetime.now(timezone.utc),
                )
        return dict(updated)

    async def list_transfers(self, *, vendor_id: UUID | None = None, limit: int = 50,
                             offset: int = 0) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select t.id, t.vendor_id, v.name as vendor_name, t.source_kind,
                          t.source_reference_id, t.razorpay_order_id, t.razorpay_transfer_id,
                          t.gross_amount_inr, t.vendor_amount_inr, t.commission_inr, t.rate_bps,
                          t.status, t.failure_reason, t.settlement_utr, t.planned_at, t.provider_event_at
                   from public.vendor_payout_transfers t
                   join public.vendors v on v.id = t.vendor_id
                   where ($1::uuid is null or t.vendor_id = $1)
                   order by t.planned_at desc
                   limit $2 offset $3""",
                vendor_id,
                limit,
                offset,
            )
        return [dict(row) for row in rows]

    async def settlement_summary(self) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select count(*) as rows,
                          coalesce(sum(vendor_amount_inr) filter (
                            where status in ('processed','settled')), 0) as routed_inr,
                          coalesce(sum(commission_inr) filter (
                            where status in ('processed','settled')), 0) as commission_inr,
                          coalesce(sum(vendor_amount_inr) filter (where status = 'planned'), 0) as planned_inr,
                          count(*) filter (where status = 'failed') as failed
                   from public.vendor_payout_transfers"""
            )
        return dict(row or {})


async def plan_payment_payout(
    pool: asyncpg.Pool,
    *,
    enabled: bool,
    vendor_id: UUID | None,
    source_kind: str,
    source_reference_id: UUID,
    gross_amount_inr: Decimal,
) -> PayoutSplit | None:
    """Split a payment for routing, or return None when it stays fully with the platform."""
    if not enabled or vendor_id is None:
        return None
    return await PayoutRepository(pool).plan_for_payment(
        payout_id=uuid4(),
        vendor_id=vendor_id,
        source_kind=source_kind,
        source_reference_id=source_reference_id,
        gross_amount_inr=gross_amount_inr,
    )


async def record_payment_payout(
    pool: asyncpg.Pool,
    split: PayoutSplit | None,
    razorpay_order_id: str,
) -> None:
    if split is None:
        return
    await PayoutRepository(pool).record_planned_transfer(split, razorpay_order_id)
