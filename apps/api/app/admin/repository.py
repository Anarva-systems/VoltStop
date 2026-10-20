import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.core.errors import ApiError
from app.finance.consistency import check_financial_consistency
from app.finance.refunds import validate_refund_amount


def row_dict(row: asyncpg.Record | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("timeline", "linked_refunds", "evidence", "metadata", "request_metadata",
                "before_state", "after_state", "permissions", "completed_stages"):
        if key in result:
            result[key] = json_value(result[key])
    return result


def json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if value is not None else {}


async def configured_commission_rate_bps(connection: asyncpg.Connection) -> int:
    try:
        rate_bps = await connection.fetchval(
            "select rate_bps from public.platform_commission_settings where id=1"
        )
    except asyncpg.UndefinedTableError as exc:
        raise ApiError(
            503,
            "PLATFORM_COMMISSION_MIGRATION_REQUIRED",
            "Apply the platform commission database migration before loading financial calculations",
        ) from exc
    if rate_bps is None:
        raise ApiError(
            503,
            "PLATFORM_COMMISSION_NOT_CONFIGURED",
            "The platform commission rate has not been configured",
        )
    return int(rate_bps)


class AdminRepository:
    """Queries and state transitions used only after AdminContext authorization."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def identity(self, user_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """select u.user_id, u.role_name, u.is_active,
                          coalesce(array_agg(rp.permission_key) filter (where rp.permission_key is not null), '{}') as permissions
                   from public.admin_users u
                   left join public.admin_role_permissions rp on rp.role_name=u.role_name
                   where u.user_id=$1 group by u.user_id""", user_id,
            )
        return row_dict(row)

    async def dashboard(self) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            commission_rate_bps = await configured_commission_rate_bps(conn)
            metrics = await conn.fetchrow(
                """select
                  (select count(*) from public.bookings) as total_bookings,
                  (select count(*) from public.vendors where is_active and is_verified) as active_vendors,
                  (select coalesce(sum(amount_inr),0) from public.payments where status='captured' and webhook_verified) as gross_booking_value,
                  (select coalesce(sum(round(greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                    * c.rate_bps::numeric/10000::numeric,2)),0)
                   from public.payment_commission_ledger c
                   join public.payments p on p.id=c.payment_id
                   left join lateral (select coalesce(sum(rf.amount_inr),0) as completed_refunds
                     from public.refunds rf where rf.payment_id=p.id and rf.status='completed') r on true
                   where p.webhook_verified and p.status in ('captured','refunded')) as platform_revenue,
                  $1::smallint as platform_commission_rate_bps,
                  (select count(*) from public.disputes where status not in ('resolved','closed')) as pending_disputes,
                  (select coalesce(sum(amount_inr),0) from public.refunds where status='completed') as refund_amount,
                  (select count(*) from public.bookings where created_at >= date_trunc('day',now())) as todays_bookings,
                  (select count(*) from public.vendor_onboarding where status in ('pending','under_review','changes_requested')) as pending_vendor_applications,
                  null::integer as active_routes,
                  (select count(*) from public.disputes where status not in ('resolved','closed')) as open_disputes""",
                commission_rate_bps,
            )
            bookings = await conn.fetch(
                """select date_trunc('day',created_at)::date as period, count(*) as value
                   from public.bookings where created_at >= now() - interval '30 days'
                   group by 1 order by 1"""
            )
            revenue = await conn.fetch(
                """select date_trunc('day',created_at)::date as period, coalesce(sum(amount_inr),0) as value
                   from public.payments where status='captured' and webhook_verified and created_at >= now() - interval '30 days'
                   group by 1 order by 1"""
            )
            vendors = await conn.fetch(
                """select date_trunc('month',created_at)::date as period, count(*) as value
                   from public.vendors where created_at >= now() - interval '12 months'
                   group by 1 order by 1"""
            )
            statuses = await conn.fetch("select status, count(*) as value from public.bookings group by status order by status")
        return {
            "metrics": row_dict(metrics),
            "bookings_over_time": [row_dict(x) for x in bookings],
            "revenue_over_time": [row_dict(x) for x in revenue],
            "vendor_growth": [row_dict(x) for x in vendors],
            "booking_status": [row_dict(x) for x in statuses],
        }

    async def vendors(self, search: str | None, status: str | None, vendor_type: str | None,
                      location: str | None, limit: int, offset: int,
                      include_financials: bool = False) -> dict[str, Any]:
        where = ["($1::text is null or v.name ilike '%'||$1||'%' or v.address ilike '%'||$1||'%')",
                 "($2::text is null or coalesce(o.status, case when v.is_verified then 'approved' else 'pending' end)=$2)",
                 "($3::text is null or v.type=$3)", "($4::text is null or v.address ilike '%'||$4||'%')"]
        where_sql = " and ".join(where)
        args = (search, status, vendor_type, location)
        async with self.pool.acquire() as conn:
            owner_email = "auth_owner.email"
            owner_join = "left join auth.users auth_owner on auth_owner.id=v.owner_id"
            where[0] = f"($1::text is null or v.name ilike '%'||$1||'%' or v.address ilike '%'||$1||'%' or coalesce({owner_email},'') ilike '%'||$1||'%')"
            where_sql = " and ".join(where)
            total = await conn.fetchval(
                f"""select count(*) from public.vendors v left join public.vendor_onboarding o on o.vendor_id=v.id
                    {owner_join}
                    where {where_sql}""", *args,
            )
            revenue_expression = "(select coalesce(sum(p.amount_inr),0) from public.bookings b join public.payments p on p.id=b.payment_id where b.vendor_id=v.id and p.status='captured' and p.webhook_verified)" if include_financials else "null::numeric"
            rows = await conn.fetch(
                f"""select v.id, v.owner_id, coalesce({owner_email},'') as owner_email,
                          v.name, v.type, v.address, v.lat, v.lng, v.is_active, v.is_verified,
                          coalesce(o.status, case when v.is_verified then 'approved' else 'pending' end) as verification_status,
                          coalesce(o.current_stage,'application') as current_stage,
                          coalesce(o.completed_stages,'[]'::jsonb) as completed_stages,
                          o.submitted_at, v.created_at,
                          (select count(*) from public.bookings b where b.vendor_id=v.id) as bookings,
                          {revenue_expression} as gross_revenue
                   from public.vendors v left join public.vendor_onboarding o on o.vendor_id=v.id
                   {owner_join}
                   where {where_sql} order by v.created_at desc limit $5 offset $6""",
                *args, limit, offset,
            )
        return {"items": [row_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    async def vendor(self, vendor_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """select v.id, v.name, v.type, v.phone, v.address, v.lat, v.lng, v.description, v.image_url,
                          v.image_url, v.operating_hours, v.is_active, v.is_verified, v.created_at,
                          coalesce(o.status, case when v.is_verified then 'approved' else 'pending' end) as verification_status,
                          o.current_stage, o.completed_stages, o.document_references, o.decision_reason, o.submitted_at,
                          coalesce((select jsonb_agg(jsonb_build_object('id',s.id,'service_type',s.service_type,
                            'display_name',s.display_name,'price_inr',s.price_inr,'capacity',s.capacity,'is_active',s.is_active)
                            order by s.service_type) from public.vendor_services s where s.vendor_id=v.id),'[]'::jsonb) as services,
                          (select count(*) from public.bookings b where b.vendor_id=v.id) as bookings
                   from public.vendors v left join public.vendor_onboarding o on o.vendor_id=v.id where v.id=$1""", vendor_id,
            )
        return row_dict(row)

    async def vendor_financials(self, vendor_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            commission_rate_bps = await configured_commission_rate_bps(conn)
            row = await conn.fetchrow(
                """with paid as (
                     select c.captured_amount_inr,
                            coalesce(r.completed_refunds,0) as completed_refunds,
                            round(greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                              * c.rate_bps::numeric/10000::numeric,2) as platform_fee
                     from public.bookings b
                     join public.payments p on p.id=b.payment_id
                     join public.payment_commission_ledger c on c.payment_id=p.id
                     left join lateral (select coalesce(sum(rf.amount_inr),0) as completed_refunds
                       from public.refunds rf where rf.payment_id=p.id and rf.status='completed') r on true
                     where b.vendor_id=$1 and p.webhook_verified and p.status in ('captured','refunded')
                   )
                   select v.id as vendor_id,v.name,
                          coalesce(sum(paid.captured_amount_inr),0) as gross_revenue,
                          coalesce(sum(paid.completed_refunds),0) as completed_refunds,
                          coalesce(sum(paid.platform_fee),0) as platform_fee,
                          coalesce(sum(greatest(paid.captured_amount_inr-paid.completed_refunds,0)-paid.platform_fee),0) as vendor_payout,
                          'calculated_only'::text as payout_status,
                          $2::smallint as commission_rate_bps
                   from public.vendors v left join paid on true
                   where v.id=$1 group by v.id,v.name""", vendor_id, commission_rate_bps,
            )
        return row_dict(row)

    async def vendor_availability(self, vendor_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select cs.id,cs.slot_start_time,cs.slot_end_time,cs.capacity,cs.price_inr,cs.status,cs.service_type,
                          (select count(*) from public.bookings b where b.slot_id=cs.id and b.status in ('pending','confirmed')) as active_bookings
                   from public.charging_slots cs where cs.vendor_id=$1 order by cs.slot_start_time desc limit 100""", vendor_id,
            )
        return [row_dict(row) or {} for row in rows]

    async def vendor_action(self, actor_id: UUID, role: str, vendor_id: UUID, action: str,
                            reason: str, metadata: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """select v.id,v.is_active,v.is_verified,coalesce(o.status,'pending') as status
                       from public.vendors v left join public.vendor_onboarding o on o.vendor_id=v.id
                       where v.id=$1 for update of v""", vendor_id,
                )
                if row is None:
                    raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor was not found")
                before = dict(row)
                status = row["status"]
                if action == "approve":
                    if status not in ("pending", "under_review", "changes_requested"):
                        raise ApiError(409, "INVALID_VENDOR_TRANSITION", "This application cannot be approved from its current state")
                    next_status, active, verified = "approved", True, True
                elif action == "request_changes":
                    if status in ("approved", "rejected", "suspended"):
                        raise ApiError(409, "INVALID_VENDOR_TRANSITION", "Changes cannot be requested from this state")
                    next_status, active, verified = "changes_requested", False, False
                elif action == "reject":
                    if status in ("approved", "suspended"):
                        raise ApiError(409, "INVALID_VENDOR_TRANSITION", "Approved vendors must be suspended instead")
                    next_status, active, verified = "rejected", False, False
                elif action == "suspend":
                    if status != "approved":
                        raise ApiError(409, "INVALID_VENDOR_TRANSITION", "Only approved vendors can be suspended")
                    next_status, active, verified = "suspended", False, True
                elif action == "reactivate":
                    if status != "suspended":
                        raise ApiError(409, "INVALID_VENDOR_TRANSITION", "Only suspended vendors can be reactivated")
                    next_status, active, verified = "approved", True, True
                elif action == "review":
                    if status not in ("pending", "changes_requested", "under_review"):
                        raise ApiError(409, "INVALID_VENDOR_TRANSITION", "This vendor cannot enter review")
                    next_status, active, verified = "under_review", False, False
                else:
                    raise ApiError(422, "INVALID_VENDOR_ACTION", "Unsupported vendor action")
                await conn.execute("update public.vendors set is_active=$2,is_verified=$3,updated_at=now() where id=$1",
                                   vendor_id, active, verified)
                await conn.execute(
                    """insert into public.vendor_onboarding(vendor_id,status,current_stage,decision_reason,reviewed_by,reviewed_at)
                       values($1,$2,case when $2='approved' then 'approval' else 'verification' end,$3,$4,now())
                       on conflict(vendor_id) do update set status=excluded.status,current_stage=excluded.current_stage,
                         decision_reason=excluded.decision_reason,reviewed_by=excluded.reviewed_by,reviewed_at=now(),updated_at=now()""",
                    vendor_id, next_status, reason, actor_id,
                )
                after = {"status": next_status, "is_active": active, "is_verified": verified}
                await self._audit(conn, actor_id, role, f"vendor.{action}", "vendor", str(vendor_id), reason,
                                  before, after, metadata)
        return await self.vendor(vendor_id) or {}

    async def bookings(self, search: str | None, status: str | None, payment_status: str | None,
                       service: str | None, vendor_id: UUID | None, start: datetime | None,
                       end: datetime | None, limit: int, offset: int) -> dict[str, Any]:
        predicates = ["($1::text is null or b.id::text ilike '%'||$1||'%' or pr.name ilike '%'||$1||'%' or v.name ilike '%'||$1||'%')",
                      "($2::text is null or b.status=$2)", "($3::text is null or p.status=$3)",
                      "($4::text is null or cs.service_type=$4)", "($5::uuid is null or b.vendor_id=$5)",
                      "($6::timestamptz is null or cs.slot_start_time >= $6)", "($7::timestamptz is null or cs.slot_start_time < $7)"]
        where = " and ".join(predicates)
        args = (search, status, payment_status, service, vendor_id, start, end)
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(
                f"""select count(*) from public.bookings b join public.profiles pr on pr.id=b.user_id
                    join public.vendors v on v.id=b.vendor_id join public.charging_slots cs on cs.id=b.slot_id
                    left join public.payments p on p.id=b.payment_id where {where}""", *args,
            )
            rows = await conn.fetch(
                f"""select b.id as booking_id,b.status,b.amount_paid,b.created_at,b.updated_at,
                          pr.name as customer_name,v.id as vendor_id,v.name as vendor_name,
                          cs.service_type,cs.slot_start_time,cs.slot_end_time,p.status as payment_status,
                          p.amount_inr,p.currency,p.razorpay_payment_id
                   from public.bookings b join public.profiles pr on pr.id=b.user_id
                   join public.vendors v on v.id=b.vendor_id join public.charging_slots cs on cs.id=b.slot_id
                   left join public.payments p on p.id=b.payment_id where {where}
                   order by b.created_at desc limit $8 offset $9""", *args, limit, offset,
            )
        return {"items": [row_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    async def booking(self, booking_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """select b.id as booking_id,b.status,b.amount_paid,b.created_at,b.updated_at,
                          pr.id as customer_id,pr.name as customer_name,v.id as vendor_id,v.name as vendor_name,
                          cs.id as slot_id,cs.service_type,cs.slot_start_time,cs.slot_end_time,cs.price_inr,
                          p.id as payment_id,p.status as payment_status,p.amount_inr,p.currency,
                          p.razorpay_payment_id,p.webhook_verified,
                          coalesce((select jsonb_agg(jsonb_build_object('event_type',e.event_type,'created_at',e.created_at,'metadata',e.metadata)
                            order by e.created_at) from public.booking_events e where e.booking_id=b.id),'[]'::jsonb) as timeline
                   from public.bookings b join public.profiles pr on pr.id=b.user_id join public.vendors v on v.id=b.vendor_id
                   join public.charging_slots cs on cs.id=b.slot_id left join public.payments p on p.id=b.payment_id
                   where b.id=$1""", booking_id,
            )
        return row_dict(row)

    async def live_operations(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select v.id as vendor_id,v.name,v.type,v.address,v.lat,v.lng,v.is_active,v.is_verified,
                          coalesce(o.status,'pending') as verification_status,
                          coalesce((select sum(greatest(cs.capacity-(select count(*) from public.bookings b
                            where b.slot_id=cs.id and b.status in ('pending','confirmed')),0))
                            from public.charging_slots cs where cs.vendor_id=v.id and cs.status='available'
                              and cs.slot_end_time>now()),0) as capacity,
                          (select count(*) from public.bookings b join public.charging_slots cs on cs.id=b.slot_id
                           where b.vendor_id=v.id and b.status in ('pending','confirmed') and cs.slot_end_time>now()) as active_bookings,
                          (select min(cs.slot_start_time) from public.charging_slots cs where cs.vendor_id=v.id
                           and cs.status='available' and cs.slot_start_time>now()) as next_available_slot
                   from public.vendors v left join public.vendor_onboarding o on o.vendor_id=v.id
                   order by v.name"""
            )
        return [row_dict(r) for r in rows]

    async def live_operation_slots(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select cs.id,cs.vendor_id,greatest(cs.capacity-(select count(*) from public.bookings b
                     where b.slot_id=cs.id and b.status in ('pending','confirmed')),0) as available_capacity
                   from public.charging_slots cs where cs.status='available' and cs.slot_end_time>now()"""
            )
        return [row_dict(r) or {} for r in rows]

    async def transactions(self, search: str | None, status: str | None, vendor_id: UUID | None,
                           start: datetime | None, end: datetime | None, minimum: Decimal | None,
                           maximum: Decimal | None, provider: str | None, limit: int, offset: int) -> dict[str, Any]:
        where = "($1::text is null or p.razorpay_payment_id ilike '%'||$1||'%' or b.id::text ilike '%'||$1||'%') and ($2::text is null or p.status=$2) and ($3::uuid is null or b.vendor_id=$3) and ($4::timestamptz is null or p.created_at >= $4) and ($5::timestamptz is null or p.created_at < $5) and ($6::numeric is null or p.amount_inr >= $6) and ($7::numeric is null or p.amount_inr <= $7) and ($8::text is null or $8='Razorpay')"
        args = (search, status, vendor_id, start, end, minimum, maximum, provider)
        async with self.pool.acquire() as conn:
            commission_rate_bps = await configured_commission_rate_bps(conn)
            total = await conn.fetchval(f"select count(*) from public.payments p join public.bookings b on b.payment_id=p.id where {where}", *args)
            rows = await conn.fetch(
                f"""select p.id as transaction_id,p.razorpay_payment_id,p.status,p.amount_inr,p.currency,p.created_at,
                          b.id as booking_id,v.id as vendor_id,v.name as vendor_name,pr.name as customer_name,
                          'Razorpay'::text as provider,
                          case when c.payment_id is not null and p.webhook_verified and p.status in ('captured','refunded')
                            then round(greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                              * c.rate_bps::numeric/10000::numeric,2) end as platform_fee_inr,
                          case when c.payment_id is not null and p.webhook_verified and p.status in ('captured','refunded')
                            then greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                              - round(greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                                * c.rate_bps::numeric/10000::numeric,2) end as vendor_payout_inr
                   from public.payments p join public.bookings b on b.payment_id=p.id
                   join public.vendors v on v.id=b.vendor_id join public.profiles pr on pr.id=b.user_id
                   left join public.payment_commission_ledger c on c.payment_id=p.id
                   left join lateral (select coalesce(sum(rf.amount_inr),0) as completed_refunds
                     from public.refunds rf where rf.payment_id=p.id and rf.status='completed') r on true
                   where {where} order by p.created_at desc limit $9 offset $10""", *args, limit, offset,
            )
        return {"items": [row_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset,
                "commission_rate_bps": commission_rate_bps,
                "fee_disclosure": f"A {commission_rate_bps / 100:g}% commission calculation policy is recorded for new verified charging payments; completed refunds reduce the calculated amount. Earlier verified payments are grandfathered at 0%. This ledger does not split customer payments or send vendor payouts; the vendor amounts shown are estimates only."}

    async def payouts(self, limit: int, offset: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            commission_rate_bps = await configured_commission_rate_bps(conn)
            total = await conn.fetchval("select count(*) from public.vendors")
            rows = await conn.fetch(
                """with paid as (
                     select b.vendor_id,c.captured_amount_inr,
                            coalesce(r.completed_refunds,0) as completed_refunds,
                            round(greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                              * c.rate_bps::numeric/10000::numeric,2) as platform_fee
                     from public.bookings b
                     join public.payments p on p.id=b.payment_id
                     join public.payment_commission_ledger c on c.payment_id=p.id
                     left join lateral (select coalesce(sum(rf.amount_inr),0) as completed_refunds
                       from public.refunds rf where rf.payment_id=p.id and rf.status='completed') r on true
                     where p.webhook_verified and p.status in ('captured','refunded')
                   ), settled AS (
                     select vendor_id,sum(captured_amount_inr) as gross_revenue,
                            sum(completed_refunds) as refunds,sum(platform_fee) as platform_fee,
                            sum(greatest(captured_amount_inr-completed_refunds,0)-platform_fee) as calculated_payout
                     from paid group by vendor_id
                   )
                   select v.id as vendor_id,v.name,
                          coalesce(s.gross_revenue,0) as gross_revenue,
                          coalesce(s.refunds,0) as refunds,
                          coalesce(s.platform_fee,0) as platform_fee,
                          coalesce(s.calculated_payout,0) as calculated_payout,
                          'calculated_only'::text as payout_status
                   from public.vendors v left join settled s on s.vendor_id=v.id
                   order by v.name limit $1 offset $2""", limit, offset,
            )
        return {"items": [row_dict(row) for row in rows], "total": total, "limit": limit, "offset": offset,
                "commission_rate_bps": commission_rate_bps,
                "notice": f"A {commission_rate_bps / 100:g}% commission calculation policy is recorded for new verified charging payments; completed refunds reduce the calculated amount. Earlier verified payments are grandfathered at 0%. This accounting ledger does not split customer payments or send money. Vendor balances are estimates; no payout ledger or transfer provider is connected, so nothing is marked paid or sent."}

    async def refunds(self, status: str | None, booking_id: UUID | None, limit: int, offset: int) -> dict[str, Any]:
        where = "($1::text is null or r.status=$1) and ($2::uuid is null or r.booking_id=$2)"
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(f"select count(*) from public.refunds r where {where}", status, booking_id)
            rows = await conn.fetch(
                f"""select r.id,r.booking_id,r.payment_id,r.amount_inr,r.currency,r.reason,r.status,
                          r.idempotency_key,r.razorpay_refund_id,r.provider_status,r.provider_error,r.created_at,r.updated_at,
                          v.name as vendor_name,pr.name as customer_name,p.razorpay_payment_id
                   from public.refunds r join public.bookings b on b.id=r.booking_id join public.vendors v on v.id=b.vendor_id
                   join public.profiles pr on pr.id=b.user_id join public.payments p on p.id=r.payment_id
                   where {where} order by r.created_at desc limit $3 offset $4""", status, booking_id, limit, offset,
            )
        return {"items": [row_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    async def refund_eligibility(self, booking_id: UUID) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """select b.id as booking_id,b.status as booking_status,p.id as payment_id,
                          p.amount_inr,p.status as payment_status,p.webhook_verified,
                          p.razorpay_payment_id,v.name as vendor_name,pr.name as customer_name,
                          coalesce((select sum(r.amount_inr) from public.refunds r where r.payment_id=p.id
                            and r.status not in ('failed','rejected')),0) as reserved_refunds,
                          coalesce((select sum(r.amount_inr) from public.refunds r where r.payment_id=p.id
                            and r.status='completed'),0) as completed_refunds,
                          exists(select 1 from public.refunds r where r.payment_id=p.id
                            and r.status in ('requested','approved','processing')) as active_refund
                   from public.bookings b join public.payments p on p.id=b.payment_id
                   join public.vendors v on v.id=b.vendor_id join public.profiles pr on pr.id=b.user_id
                   where b.id=$1""", booking_id,
            )
        if row is None:
            raise ApiError(404, "BOOKING_NOT_FOUND", "Booking or payment was not found")
        result = row_dict(row) or {}
        remaining = max(Decimal(result["amount_inr"]) - Decimal(result["reserved_refunds"]), Decimal("0"))
        result["completed_refunds"] = Decimal(result["completed_refunds"])
        result["previously_refunded_amount"] = Decimal(result["completed_refunds"])
        result["remaining_refundable_amount"] = remaining
        result["eligible"] = bool(result["payment_status"] == "captured" and result["webhook_verified"]
                                  and result["razorpay_payment_id"] and not result["active_refund"] and remaining > 0)
        return result

    async def create_refund_request(self, actor_id: UUID, booking_id: UUID, amount: Decimal | None,
                                    reason: str, idempotency_key: str, role: str,
                                    metadata: dict[str, Any], dispute_id: UUID | None = None) -> tuple[dict[str, Any], bool]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                booking = await conn.fetchrow(
                    """select b.id,b.status,b.vendor_id,b.payment_id,p.amount_inr,p.status as payment_status,
                              p.webhook_verified,p.razorpay_payment_id
                       from public.bookings b join public.payments p on p.id=b.payment_id
                       where b.id=$1 for update of b,p""", booking_id,
                )
                if booking is None:
                    raise ApiError(404, "BOOKING_NOT_FOUND", "Booking or payment was not found")
                if booking["payment_status"] != "captured" or not booking["webhook_verified"] or not booking["razorpay_payment_id"]:
                    raise ApiError(409, "REFUND_NOT_ELIGIBLE", "Only captured, webhook-verified Razorpay payments can be refunded")
                if dispute_id is not None:
                    dispute = await conn.fetchrow(
                        "select id,booking_id,status from public.disputes where id=$1 for update", dispute_id,
                    )
                    if dispute is None or dispute["booking_id"] != booking_id:
                        raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found for this booking")
                    if dispute["status"] in ("resolved", "closed"):
                        raise ApiError(409, "DISPUTE_CLOSED", "A refund cannot be requested for a closed dispute")
                existing = await conn.fetchrow(
                    """select r.*,p.razorpay_payment_id from public.refunds r
                       join public.payments p on p.id=r.payment_id where r.idempotency_key=$1""", idempotency_key
                )
                if existing is not None:
                    if (existing["booking_id"] != booking_id
                            or (amount is not None and Decimal(existing["amount_inr"]) != amount)
                            or existing["reason"] != reason or existing["dispute_id"] != dispute_id):
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This idempotency key was used for a different refund")
                    return row_dict(existing) or {}, False
                refunded = await conn.fetchval(
                    "select coalesce(sum(amount_inr),0) from public.refunds where payment_id=$1 and status not in ('failed','rejected')",
                    booking["payment_id"],
                )
                requested_amount, _remaining_after = validate_refund_amount(
                    Decimal(booking["amount_inr"]), Decimal(refunded), amount,
                )
                active = await conn.fetchval(
                    "select exists(select 1 from public.refunds where payment_id=$1 and status in ('requested','approved','processing'))",
                    booking["payment_id"],
                )
                if active:
                    raise ApiError(409, "REFUND_ALREADY_IN_PROGRESS", "A refund for this payment is already in progress")
                inserted = await conn.fetchrow(
                    """insert into public.refunds(booking_id,payment_id,requested_by,amount_inr,reason,status,idempotency_key,dispute_id)
                       values($1,$2,$3,$4,$5,'requested',$6,$7) returning *""",
                    booking_id, booking["payment_id"], actor_id, requested_amount, reason, idempotency_key, dispute_id,
                )
                result = row_dict(inserted) or {}
                result["razorpay_payment_id"] = booking["razorpay_payment_id"]
                await self._audit(conn, actor_id, role, "refund.requested", "refund", str(result["id"]), reason,
                                  None, {"booking_id": str(booking_id), "amount_inr": str(requested_amount),
                                         "status": "requested"}, metadata)
                if dispute_id is not None:
                    await conn.execute(
                        """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,message,metadata,idempotency_key)
                           values($1,$2,$2,'admin','refund_requested',$3,$4::jsonb,$5)""",
                        dispute_id, actor_id, reason, json.dumps({"refund_id": str(result["id"]), "amount_inr": str(requested_amount)}),
                        f"{idempotency_key}:dispute",
                    )
                    await self._audit(conn, actor_id, role, "dispute.refund_requested", "dispute", str(dispute_id), reason,
                                      None, {"refund_id": str(result["id"]), "amount_inr": str(requested_amount)}, metadata)
                return result, True

    async def approve_refund_request(self, actor_id: UUID, role: str, refund_id: UUID,
                                    reason: str, metadata: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """select r.*,p.amount_inr as captured_amount,p.status as payment_status,
                              p.webhook_verified,p.razorpay_payment_id
                       from public.refunds r join public.payments p on p.id=r.payment_id
                       where r.id=$1 for update of r,p""", refund_id,
                )
                if row is None:
                    raise ApiError(404, "REFUND_NOT_FOUND", "Refund was not found")
                if row["status"] != "requested":
                    raise ApiError(409, "REFUND_NOT_REQUESTED", "Only requested refunds can be approved")
                if row["payment_status"] != "captured" or not row["webhook_verified"] or not row["razorpay_payment_id"]:
                    raise ApiError(409, "REFUND_NOT_ELIGIBLE", "The captured payment is no longer eligible for refund")
                reserved = await conn.fetchval(
                    """select coalesce(sum(amount_inr),0) from public.refunds
                       where payment_id=$1 and id<>$2 and status not in ('failed','rejected')""",
                    row["payment_id"], refund_id,
                )
                validate_refund_amount(Decimal(row["captured_amount"]), Decimal(reserved), Decimal(row["amount_inr"]))
                other_active = await conn.fetchval(
                    """select exists(select 1 from public.refunds where payment_id=$1 and id<>$2
                       and status in ('approved','processing'))""", row["payment_id"], refund_id,
                )
                if other_active:
                    raise ApiError(409, "REFUND_ALREADY_IN_PROGRESS", "Another refund for this payment is already approved or processing")
                updated = await conn.fetchrow(
                    """update public.refunds set status='approved',approved_by=$2,approved_at=now(),updated_at=now()
                       where id=$1 returning *""", refund_id, actor_id,
                )
                await self._audit(conn, actor_id, role, "refund.approved", "refund", str(refund_id), reason,
                                  {"status": "requested"}, {"status": "approved", "amount_inr": str(row["amount_inr"])}, metadata)
                if row["dispute_id"]:
                    await conn.execute(
                        """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,message,metadata)
                           values($1,$2,$2,'admin','refund_approved',$3,$4::jsonb)""",
                        row["dispute_id"], actor_id, reason, json.dumps({"refund_id": str(refund_id), "amount_inr": str(row["amount_inr"])}),
                    )
                    await self._audit(conn, actor_id, role, "dispute.refund_approved", "dispute", str(row["dispute_id"]), reason,
                                      {"refund_status": "requested"}, {"refund_status": "approved"}, metadata)
                result = row_dict(updated) or {}
                result["razorpay_payment_id"] = row["razorpay_payment_id"]
                return result

    async def reject_refund_request(self, actor_id: UUID, role: str, refund_id: UUID,
                                   reason: str, metadata: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("select * from public.refunds where id=$1 for update", refund_id)
                if row is None:
                    raise ApiError(404, "REFUND_NOT_FOUND", "Refund was not found")
                if row["status"] != "requested":
                    raise ApiError(409, "REFUND_NOT_REQUESTED", "Only requested refunds can be rejected")
                updated = await conn.fetchrow(
                    "update public.refunds set status='rejected',updated_at=now() where id=$1 returning *", refund_id,
                )
                await self._audit(conn, actor_id, role, "refund.rejected", "refund", str(refund_id), reason,
                                  {"status": "requested"}, {"status": "rejected"}, metadata)
                if row["dispute_id"]:
                    await conn.execute(
                        """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,message,metadata)
                           values($1,$2,$2,'admin','refund_rejected',$3,$4::jsonb)""",
                        row["dispute_id"], actor_id, reason, json.dumps({"refund_id": str(refund_id)}),
                    )
                return row_dict(updated) or {}

    async def claim_refund_for_processing(self, actor_id: UUID, role: str, refund_id: UUID,
                                          metadata: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """select r.*,p.status as payment_status,p.webhook_verified,p.razorpay_payment_id
                       from public.refunds r join public.payments p on p.id=r.payment_id
                       where r.id=$1 for update of r,p""", refund_id,
                )
                if row is None:
                    raise ApiError(404, "REFUND_NOT_FOUND", "Refund was not found")
                if row["status"] != "approved":
                    return row_dict(row) or {}, False
                if row["payment_status"] != "captured" or not row["webhook_verified"] or not row["razorpay_payment_id"]:
                    raise ApiError(409, "REFUND_NOT_ELIGIBLE", "The captured payment is no longer eligible for refund")
                updated = await conn.fetchrow(
                    "update public.refunds set status='processing',updated_at=now() where id=$1 returning *", refund_id,
                )
                await self._audit(conn, actor_id, role, "refund.submission_started", "refund", str(refund_id), None,
                                  {"status": "approved"}, {"status": "processing"}, metadata)
                if row["dispute_id"]:
                    await conn.execute(
                        """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,message,metadata)
                           values($1,$2,$2,'admin','refund_submitted','Refund submitted to the payment provider',$3::jsonb)""",
                        row["dispute_id"], actor_id, json.dumps({"refund_id": str(refund_id)}),
                    )
                result = row_dict(updated) or {}
                result["razorpay_payment_id"] = row["razorpay_payment_id"]
                return result, True

    async def finish_refund(self, refund_id: UUID, provider_id: str | None, provider_status: str,
                            status: str, actor_id: UUID, role: str,
                            metadata: dict[str, Any], provider_error: str | None = None) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """update public.refunds set razorpay_refund_id=coalesce($2,razorpay_refund_id),
                         provider_status=$3,status=$4,provider_error=$5,updated_at=now()
                       where id=$1 returning *""", refund_id, provider_id, provider_status, status,
                    provider_error[:1000] if provider_error else None,
                )
                if row is None:
                    raise ApiError(404, "REFUND_NOT_FOUND", "Refund was not found")
                await self._audit(conn, actor_id, role, "refund.provider_state", "refund", str(refund_id),
                                  provider_error, {"status": "processing"},
                                  {"status": status, "provider_status": provider_status,
                                   "razorpay_refund_id": provider_id}, metadata)
                if row["dispute_id"] and status in ("completed", "failed"):
                    event_type = "refund_completed" if status == "completed" else "refund_failed"
                    await conn.execute(
                        """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,message,metadata)
                           values($1,$2,$2,'admin',$3,$4,$5::jsonb)""",
                        row["dispute_id"], actor_id, event_type, provider_error or f"Refund {status}",
                        json.dumps({"refund_id": str(refund_id), "provider_status": provider_status}),
                    )
                if status == "completed":
                    total = await conn.fetchval(
                        "select coalesce(sum(amount_inr),0) from public.refunds where payment_id=$1 and status='completed'",
                        row["payment_id"],
                    )
                    amount = await conn.fetchval("select amount_inr from public.payments where id=$1", row["payment_id"])
                    if Decimal(total) >= Decimal(amount):
                        await conn.execute("update public.payments set status='refunded',updated_at=now() where id=$1", row["payment_id"])
                return row_dict(row) or {}

    async def disputes(self, status: str | None, limit: int, offset: int,
                       vendor_id: UUID | None = None, customer_id: UUID | None = None,
                       date_from: datetime | None = None, date_to: datetime | None = None,
                       minimum_amount: Decimal | None = None, maximum_amount: Decimal | None = None,
                       reason: str | None = None) -> dict[str, Any]:
        where = "($1::text is null or d.status=$1) and ($2::uuid is null or d.vendor_id=$2) and ($3::uuid is null or d.customer_id=$3) and ($4::timestamptz is null or d.created_at >= $4) and ($5::timestamptz is null or d.created_at < $5) and ($6::numeric is null or d.amount_inr >= $6) and ($7::numeric is null or d.amount_inr <= $7) and ($8::text is null or d.reason ilike '%' || $8 || '%')"
        args = (status, vendor_id, customer_id, date_from, date_to, minimum_amount, maximum_amount, reason)
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(f"select count(*) from public.disputes d where {where}", *args)
            rows = await conn.fetch(
                f"""select d.id,d.booking_id,d.customer_id,d.vendor_id,d.reason,d.description,d.status,d.created_at,d.updated_at,
                          d.amount_inr,pr.name as customer_name,v.name as vendor_name
                   from public.disputes d join public.bookings b on b.id=d.booking_id
                   left join public.payments p on p.id=b.payment_id
                   join public.profiles pr on pr.id=b.user_id join public.vendors v on v.id=b.vendor_id
                   where {where} order by d.created_at desc limit $9 offset $10""",
                *args, limit, offset,
            )
        return {"items": [row_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    async def dispute(self, dispute_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """select d.id,d.booking_id,d.customer_id,d.vendor_id,d.reason,d.description,d.status,d.evidence,d.resolution,
                          d.amount_inr,d.created_at,d.updated_at,d.resolved_at,d.resolved_by,
                          b.status as booking_status,b.created_at as booking_created_at,
                          p.status as payment_status,p.amount_inr as payment_amount,p.razorpay_payment_id,
                          pr.name as customer_name,pr.phone as customer_phone,v.id as vendor_id,v.name as vendor_name,v.phone as vendor_phone,
                          coalesce((select jsonb_agg(jsonb_build_object('event_type',e.event_type,'actor_type',e.actor_type,'message',e.message,'metadata',e.metadata,'created_at',e.created_at)
                            order by e.created_at) from public.dispute_events e where e.dispute_id=d.id),'[]'::jsonb) as timeline,
                          coalesce((select jsonb_agg(jsonb_build_object('id',r.id,'amount_inr',r.amount_inr,'status',r.status,'reason',r.reason,'created_at',r.created_at)
                            order by r.created_at desc) from public.refunds r where r.dispute_id=d.id),'[]'::jsonb) as linked_refunds
                   from public.disputes d join public.bookings b on b.id=d.booking_id
                   join public.profiles pr on pr.id=b.user_id join public.vendors v on v.id=b.vendor_id
                   left join public.payments p on p.id=b.payment_id where d.id=$1""", dispute_id,
            )
        return row_dict(row)

    async def create_dispute(self, actor_id: UUID, role: str, booking_id: UUID, reason: str,
                             description: str, metadata: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                replay = await conn.fetchrow(
                    """select e.dispute_id,e.message,d.booking_id,d.reason from public.dispute_events e
                       join public.disputes d on d.id=e.dispute_id where e.idempotency_key=$1""", idempotency_key,
                )
                if replay:
                    if replay["message"] != description or replay["booking_id"] != booking_id or replay["reason"] != reason:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different dispute")
                    return {"id": str(replay["dispute_id"]), "replayed": True}
                booking = await conn.fetchrow(
                    """select b.id,b.user_id,b.vendor_id,p.amount_inr from public.bookings b
                       left join public.payments p on p.id=b.payment_id where b.id=$1 for update of b""", booking_id,
                )
                if booking is None:
                    raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
                active = await conn.fetchval(
                    """select exists(select 1 from public.disputes where booking_id=$1
                       and status in ('open','investigating','awaiting_customer','awaiting_vendor'))""", booking_id,
                )
                if active:
                    raise ApiError(409, "ACTIVE_DISPUTE_EXISTS", "This booking already has an active dispute")
                row = await conn.fetchrow(
                    """insert into public.disputes(booking_id,customer_id,vendor_id,amount_inr,reason,description,created_by)
                       values($1,$2,$3,$4,$5,$6,$7) returning *""",
                    booking_id, booking["user_id"], booking["vendor_id"], booking["amount_inr"] or Decimal("0"),
                    reason, description, actor_id,
                )
                await conn.execute(
                    """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,message,metadata,idempotency_key)
                       values($1,$2,$2,'admin','created',$3,$4::jsonb,$5)""",
                    row["id"], actor_id, description, json.dumps({"source": "admin"}), idempotency_key,
                )
                await self._audit(conn, actor_id, role, "dispute.opened", "dispute", str(row["id"]), description,
                                  None, {"status": "open", "booking_id": str(booking_id)}, metadata)
        return await self.dispute(row["id"]) or {}

    async def dispute_action(self, actor_id: UUID, role: str, dispute_id: UUID, action: str,
                             message: str, metadata: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        states = {"investigate": "investigating", "await_customer": "awaiting_customer",
                  "await_vendor": "awaiting_vendor", "resolve": "resolved", "reject": "closed", "close": "closed", "note": None, "escalate": None}
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                replay = await conn.fetchrow("select dispute_id,message,metadata from public.dispute_events where idempotency_key=$1", idempotency_key)
                if replay:
                    if replay["dispute_id"] != dispute_id or replay["message"] != message or json_value(replay["metadata"]).get("action") != action:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different dispute event")
                    current = await conn.fetchrow("select id,status from public.disputes where id=$1", dispute_id)
                    return row_dict(current) or {}
                row = await conn.fetchrow("select * from public.disputes where id=$1 for update", dispute_id)
                if row is None:
                    raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
                if row["status"] == "closed" and action != "note":
                    raise ApiError(409, "DISPUTE_CLOSED", "Closed disputes cannot be changed")
                if action in ("resolve", "close", "reject"):
                    active_refund = await conn.fetchval(
                        """select exists(select 1 from public.refunds where dispute_id=$1
                           and status in ('requested','approved','processing'))""", dispute_id,
                    )
                    if active_refund:
                        raise ApiError(409, "DISPUTE_REFUND_PENDING", "Resolve or close the case after its refund reaches a final state")
                next_status = states[action]
                if next_status:
                    await conn.execute(
                        """update public.disputes set status=$2,
                             resolution=case when $2='resolved' then $3 else resolution end,
                             resolved_at=case when $2='resolved' then now() when $2='closed' then resolved_at else null end,
                             resolved_by=case when $2='resolved' then $4 when $2='closed' then resolved_by else null end,
                             updated_at=now() where id=$1""",
                        dispute_id, next_status, message, actor_id,
                    )
                event_type = ("resolved" if action == "resolve" else "closed" if action in ("close", "reject")
                              else "admin_note" if action in ("note", "escalate") else "status_changed")
                await conn.execute(
                    """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,message,metadata,idempotency_key)
                       values($1,$2,$2,'admin',$3,$4,$5::jsonb,$6)""",
                    dispute_id, actor_id, event_type, message, json.dumps({"action": action}), idempotency_key,
                )
                await self._audit(conn, actor_id, role, f"dispute.{action}", "dispute", str(dispute_id), message,
                                  {"status": row["status"]}, {"status": next_status or row["status"]}, metadata)
        return await self.dispute(dispute_id) or {}

    async def audit(self, entity_type: str | None, action: str | None, entity_id: str | None,
                    limit: int, offset: int) -> dict[str, Any]:
        where = "($1::text is null or entity_type=$1) and ($2::text is null or action=$2) and ($3::text is null or entity_id=$3)"
        async with self.pool.acquire() as conn:
            total = await conn.fetchval(f"select count(*) from public.admin_audit_logs where {where}", entity_type, action, entity_id)
            rows = await conn.fetch(
                f"select id,admin_user_id,role_name,action,entity_type,entity_id,reason,before_state,after_state,request_metadata,created_at from public.admin_audit_logs where {where} order by created_at desc limit $4 offset $5",
                entity_type, action, entity_id, limit, offset,
            )
        return {"items": [row_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    async def financial_diagnostics(self, limit: int = 5000) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select b.id as booking_id,b.status as booking_status,b.amount_paid as booking_amount,
                          p.id as payment_id,p.status as payment_status,p.amount_inr as payment_amount,
                          p.webhook_verified,
                          coalesce((select sum(r.amount_inr) from public.refunds r where r.payment_id=p.id
                            and r.status not in ('failed','rejected')),0) as reserved_refund_amount
                          ,coalesce((select sum(r.amount_inr) from public.refunds r where r.payment_id=p.id
                            and r.status='completed'),0) as completed_refund_amount
                   from public.bookings b left join public.payments p on p.id=b.payment_id
                   order by b.created_at desc limit $1""", limit + 1,
            )
        truncated = len(rows) > limit
        rows = rows[:limit]
        findings = []
        for row in rows:
            findings.extend(check_financial_consistency(row_dict(row) or {}))
        counts: dict[str, int] = {}
        for finding in findings:
            counts[finding["code"]] = counts.get(finding["code"], 0) + 1
        return {"findings": findings, "finding_counts": counts, "checked_bookings": len(rows),
                "truncated": truncated, "payout_check_available": False,
                "notice": "No payout ledger exists, so payout-to-revenue checks are unavailable."}

    async def log_action(self, actor_id: UUID, role: str, action: str, entity_type: str,
                         entity_id: str | None, reason: str | None, before: dict[str, Any] | None,
                         after: dict[str, Any] | None, metadata: dict[str, Any] | None) -> None:
        async with self.pool.acquire() as conn:
            await self._audit(conn, actor_id, role, action, entity_type, entity_id, reason, before, after, metadata)

    async def role_matrix(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select r.name,r.description,coalesce(array_agg(rp.permission_key) filter(where rp.permission_key is not null),'{}') as permissions
                   from public.admin_roles r left join public.admin_role_permissions rp on rp.role_name=r.name
                   group by r.name order by r.name"""
            )
        return [row_dict(r) or {} for r in rows]

    async def admin_users(self, limit: int, offset: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            total = await conn.fetchval("select count(*) from public.admin_users")
            rows = await conn.fetch(
                """select u.user_id,u.role_name,u.is_active,u.created_at,u.updated_at,auth_user.email as email
                   from public.admin_users u left join auth.users auth_user on auth_user.id=u.user_id
                   order by u.created_at desc limit $1 offset $2""", limit, offset,
            )
        return {"items": [row_dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    async def update_admin_user(self, actor_id: UUID, role: str, target_id: UUID, role_name: str,
                                is_active: bool, reason: str, metadata: dict[str, Any]) -> dict[str, Any]:
        if actor_id == target_id and not is_active:
            raise ApiError(409, "CANNOT_DISABLE_SELF", "You cannot disable your own admin account")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("select pg_advisory_xact_lock(hashtext('voltstop-admin-users'))")
                row = await conn.fetchrow("select * from public.admin_users where user_id=$1 for update", target_id)
                if row is None:
                    raise ApiError(404, "ADMIN_USER_NOT_FOUND", "Administrator account was not found")
                before = dict(row)
                if before["role_name"] == "SUPER_ADMIN" and before["is_active"] and (role_name != "SUPER_ADMIN" or not is_active):
                    count = await conn.fetchval("select count(*) from public.admin_users where role_name='SUPER_ADMIN' and is_active")
                    if count <= 1:
                        raise ApiError(409, "LAST_SUPER_ADMIN", "At least one active super administrator must remain")
                updated = await conn.fetchrow(
                    "update public.admin_users set role_name=$2,is_active=$3,updated_at=now() where user_id=$1 returning *",
                    target_id, role_name, is_active,
                )
                await self._audit(conn, actor_id, role, "admin_user.permissions_changed", "admin_user", str(target_id),
                                  reason, before, dict(updated), metadata)
        return row_dict(updated) or {}

    async def _audit(self, conn: asyncpg.Connection, actor_id: UUID, role: str, action: str,
                     entity_type: str, entity_id: str | None, reason: str | None,
                     before: dict[str, Any] | None, after: dict[str, Any] | None,
                     metadata: dict[str, Any] | None) -> None:
        await conn.execute(
            """insert into public.admin_audit_logs(admin_user_id,role_name,action,entity_type,entity_id,reason,before_state,after_state,request_metadata)
               values($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9::jsonb)""",
            actor_id, role, action, entity_type, entity_id, reason,
            json.dumps(before, default=str) if before is not None else None,
            json.dumps(after, default=str) if after is not None else None,
            json.dumps(metadata or {}, default=str),
        )
