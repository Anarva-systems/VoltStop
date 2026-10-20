from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.admin.auth import AdminContext, require_permission
from app.core.config import get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success

router = APIRouter(prefix="/admin", tags=["admin-portal-pages"])


class ServiceAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    price_inr: float | None = Field(default=None, ge=0, le=10000000)
    reason: str = Field(min_length=8, max_length=1000)


@router.get("/customers")
async def customers(_admin: Annotated[AdminContext, Depends(require_permission("customers:read"))],
                    database: DatabaseDependency,
                    q: str | None = Query(default=None, max_length=160),
                    status: str | None = Query(default=None, pattern="^(active|banned|unknown)$"),
                    limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    search = q.strip() if q and q.strip() else None
    async with database.pool.acquire() as conn:
        auth_join = "join auth.users u on u.id=p.id"
        account_status = "case when u.banned_until is not null and u.banned_until > now() then 'banned' else 'active' end"
        profile_email = "u.email"
        profile_phone = "coalesce(nullif(u.phone,''),nullif(p.phone,''))"
        status_filter = f"{account_status}=$2"
        # profiles is created for every Auth account, including email-only vendor
        # and admin accounts. The Customers directory contains phone-authenticated
        # accounts only; vendor profiles are listed from public.vendors instead.
        where = f"{profile_phone} is not null and ($1::text is null or p.name ilike '%'||$1||'%' or {profile_email} ilike '%'||$1||'%' or {profile_phone} ilike '%'||$1||'%' or p.id::text ilike '%'||$1||'%') and ($2::text is null or {status_filter})"
        total = await conn.fetchval(f"select count(*) from public.profiles p {auth_join} where {where}", search, status)
        rows = await conn.fetch(
            f"""select p.id,p.name,{profile_email} as email,{profile_phone} as phone,p.created_at,{account_status} as account_status,
                      (select count(*) from public.bookings b where b.user_id=p.id) as booking_count,
                      (select count(*) from public.disputes d where d.customer_id=p.id) as complaint_count
               from public.profiles p {auth_join} where {where}
               order by p.created_at desc limit $3 offset $4""", search, status, limit, offset,
        )
    return success({"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset})


@router.get("/customers/{customer_id}")
async def customer_detail(customer_id: UUID, _admin: Annotated[AdminContext, Depends(require_permission("customers:read"))],
                          database: DatabaseDependency) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        profile = await conn.fetchrow(
            """select p.id,p.name,u.email,coalesce(nullif(u.phone,''),nullif(p.phone,'')) as phone,p.created_at,p.updated_at,u.banned_until,
                      case when u.banned_until is not null and u.banned_until > now() then 'banned' else 'active' end as account_status
               from public.profiles p join auth.users u on u.id=p.id
               where p.id=$1 and coalesce(nullif(u.phone,''),nullif(p.phone,'')) is not null""", customer_id,
        )
        if not profile:
            raise ApiError(404, "CUSTOMER_NOT_FOUND", "Customer was not found")
        bookings = await conn.fetch(
            """select b.id,b.vendor_id,v.name as vendor_name,b.status,b.amount_paid as amount_inr,b.created_at,
                      p.status as payment_status,p.webhook_verified
               from public.bookings b join public.vendors v on v.id=b.vendor_id left join public.payments p on p.id=b.payment_id
               where b.user_id=$1 order by b.created_at desc limit 100""", customer_id,
        )
        disputes = await conn.fetch(
            "select id,booking_id,reason,status,created_at,updated_at from public.disputes where customer_id=$1 order by created_at desc limit 100",
            customer_id,
        )
        hotel_ready = await conn.fetchval("select to_regclass('public.hotel_reservations') is not null")
        restaurant_ready = await conn.fetchval("select to_regclass('public.restaurant_orders') is not null")
        hotel_reservations = []
        restaurant_orders = []
        if hotel_ready:
            hotel_reservations = await conn.fetch(
                """select hr.id,hr.vendor_id,v.name as vendor_name,rt.name as room_type,hr.check_in,hr.check_out,
                          hr.guests,hr.rooms,hr.amount_inr,hr.status,hr.created_at
                   from public.hotel_reservations hr join public.vendors v on v.id=hr.vendor_id
                   join public.hotel_room_types rt on rt.id=hr.room_type_id
                   where hr.customer_id=$1 order by hr.created_at desc limit 100""", customer_id,
            )
        if restaurant_ready:
            restaurant_orders = await conn.fetch(
                """select ro.id,ro.vendor_id,v.name as vendor_name,ro.status,ro.total_inr as amount_inr,
                          ro.fulfillment_method,ro.created_at
                   from public.restaurant_orders ro join public.vendors v on v.id=ro.vendor_id
                   where ro.customer_id=$1 order by ro.created_at desc limit 100""", customer_id,
            )
    return success({**dict(profile), "bookings": [dict(row) for row in bookings], "complaints": [dict(row) for row in disputes],
                    "hotel_reservations": [dict(row) for row in hotel_reservations],
                    "restaurant_orders": [dict(row) for row in restaurant_orders],
                    "hotel_schema_configured": hotel_ready, "restaurant_schema_configured": restaurant_ready})


@router.get("/availability")
async def availability(_admin: Annotated[AdminContext, Depends(require_permission("availability:read"))],
                       database: DatabaseDependency,
                       vendor_id: UUID | None = None,
                       start: datetime | None = None,
                       end: datetime | None = None,
                       limit: int = Query(default=100, ge=1, le=250), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    if (start is not None and start.utcoffset() is None) or (end is not None and end.utcoffset() is None):
        raise ApiError(422, "TIMEZONE_REQUIRED", "Availability date filters must include a timezone")
    if start is not None and end is not None and start >= end:
        raise ApiError(422, "INVALID_DATE_RANGE", "Availability start must be before end")
    async with database.pool.acquire() as conn:
        rows = await conn.fetch(
            """select cs.id,cs.vendor_id,v.name as vendor_name,v.type as vendor_type,cs.service_type,
                      cs.slot_start_time,cs.slot_end_time,cs.capacity,cs.price_inr,cs.status,
                      (select count(*) from public.bookings b where b.slot_id=cs.id and b.status in ('pending','confirmed')) as active_bookings
               from public.charging_slots cs join public.vendors v on v.id=cs.vendor_id
               where ($1::uuid is null or cs.vendor_id=$1)
                 and ($2::timestamptz is null or cs.slot_start_time >= $2)
                 and ($3::timestamptz is null or cs.slot_start_time < $3)
               order by cs.slot_start_time desc limit $4 offset $5""", vendor_id, start, end, limit, offset,
        )
        total = await conn.fetchval(
            """select count(*) from public.charging_slots cs where ($1::uuid is null or cs.vendor_id=$1)
                 and ($2::timestamptz is null or cs.slot_start_time >= $2) and ($3::timestamptz is null or cs.slot_start_time < $3)""",
            vendor_id, start, end,
        )
        hotel_ready = await conn.fetchval("select to_regclass('public.hotel_room_inventory') is not null")
        restaurant_ready = await conn.fetchval("select to_regclass('public.restaurant_menu_items') is not null")
        hotel_inventory = []
        restaurant_availability = []
        if hotel_ready:
            hotel_inventory = await conn.fetch(
                """select rt.id as room_type_id,rt.vendor_id,v.name as vendor_name,rt.name as room_type,
                          ri.stay_date,ri.room_capacity,ri.rooms_available,ri.nightly_rate_inr,
                          coalesce((select sum(n.rooms) from public.hotel_reservation_nights n
                            join public.hotel_reservations r on r.id=n.reservation_id
                            where n.room_type_id=rt.id and n.stay_date=ri.stay_date
                              and r.status in ('payment_pending','confirmed','refund_pending')),0) as reserved_rooms
                   from public.hotel_room_inventory ri join public.hotel_room_types rt on rt.id=ri.room_type_id
                   join public.vendors v on v.id=rt.vendor_id
                   where ri.stay_date >= coalesce($1::timestamptz::date,current_date)
                     and ($2::timestamptz is null or ri.stay_date < $2::timestamptz::date)
                     and ($3::uuid is null or rt.vendor_id=$3)
                   order by ri.stay_date,v.name limit $4 offset $5""", start, end, vendor_id, limit, offset,
            )
        if restaurant_ready:
            restaurant_availability = await conn.fetch(
                """select i.id as item_id,i.vendor_id,v.name as vendor_name,i.name as item_name,
                          i.is_available,i.updated_at from public.restaurant_menu_items i
                   join public.vendors v on v.id=i.vendor_id where ($1::uuid is null or i.vendor_id=$1)
                   order by v.name,i.name limit $2 offset $3""", vendor_id, limit, offset,
            )
    return success({"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset,
                    "hotel_inventory_configured": hotel_ready, "hotel_inventory": [dict(row) for row in hotel_inventory],
                    "restaurant_menu_configured": restaurant_ready,
                    "restaurant_availability": [dict(row) for row in restaurant_availability]})


@router.get("/services")
async def services(_admin: Annotated[AdminContext, Depends(require_permission("services:read"))],
                   database: DatabaseDependency,
                   q: str | None = Query(default=None, max_length=160),
                   vendor_type: str | None = Query(default=None, pattern="^(hotel|restaurant)$"),
                   limit: int = Query(default=100, ge=1, le=250), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    search = q.strip() if q and q.strip() else None
    async with database.pool.acquire() as conn:
        rows = await conn.fetch(
            """select s.id,s.vendor_id,v.name as vendor_name,v.type as vendor_type,v.is_active as vendor_active,
                      v.is_verified,s.service_type,s.display_name,s.description,s.price_inr,s.capacity,s.is_active,s.updated_at
               from public.vendor_services s join public.vendors v on v.id=s.vendor_id
               where ($1::text is null or v.type=$1) and ($2::text is null or v.name ilike '%'||$2||'%' or s.display_name ilike '%'||$2||'%')
               order by v.name,s.service_type limit $3 offset $4""", vendor_type, search, limit, offset,
        )
        total = await conn.fetchval(
            "select count(*) from public.vendor_services s join public.vendors v on v.id=s.vendor_id where ($1::text is null or v.type=$1) and ($2::text is null or v.name ilike '%'||$2||'%' or s.display_name ilike '%'||$2||'%')",
            vendor_type, search,
        )
    return success({"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset})


@router.patch("/services/{service_id}")
async def update_service(service_id: UUID, payload: ServiceAction, request: Request,
                         admin: Annotated[AdminContext, Depends(require_permission("services:manage"))],
                         database: DatabaseDependency) -> dict[str, Any]:
    if payload.is_active is None and payload.price_inr is None:
        raise ApiError(422, "EMPTY_SERVICE_UPDATE", "A service status or price change is required")
    async with database.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "select s.*,v.name as vendor_name,v.is_active as vendor_active,v.is_verified from public.vendor_services s join public.vendors v on v.id=s.vendor_id where s.id=$1 for update of s,v",
                service_id,
            )
            if not row:
                raise ApiError(404, "SERVICE_NOT_FOUND", "Vendor service was not found")
            if payload.is_active and (not row["vendor_active"] or not row["is_verified"]):
                raise ApiError(409, "VENDOR_NOT_PUBLISHABLE", "A suspended or unverified vendor service cannot be activated")
            before = {"is_active": row["is_active"], "price_inr": str(row["price_inr"])}
            active = row["is_active"] if payload.is_active is None else payload.is_active
            price = row["price_inr"] if payload.price_inr is None else payload.price_inr
            updated = await conn.fetchrow(
                "update public.vendor_services set is_active=$2,price_inr=$3,updated_at=now() where id=$1 returning id,vendor_id,service_type,display_name,price_inr,is_active,updated_at",
                service_id, active, Decimal(str(price)),
            )
            after = {"is_active": active, "price_inr": str(price)}
            await conn.execute(
                """insert into public.admin_audit_logs(admin_user_id,role_name,action,entity_type,entity_id,reason,before_state,after_state,request_metadata)
                   values($1,$2,'vendor_service.updated','vendor_service',$3,$4,$5::jsonb,$6::jsonb,$7::jsonb)""",
                admin.user_id, admin.role_name, str(service_id), payload.reason, _json(before), _json(after),
                _json({"ip": request.client.host if request.client else None, "user_agent": request.headers.get("user-agent", "")[:500]}),
            )
    return success(dict(updated), "Vendor service updated")


@router.get("/pricing")
async def pricing(_admin: Annotated[AdminContext, Depends(require_permission("pricing:read"))],
                  database: DatabaseDependency, limit: int = Query(default=100, ge=1, le=250),
                  offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        services = await conn.fetch(
            """select s.id,s.vendor_id,v.name as vendor_name,v.type as vendor_type,s.service_type,s.display_name,
                      s.price_inr,s.is_active,s.updated_at from public.vendor_services s join public.vendors v on v.id=s.vendor_id
               order by s.updated_at desc limit $1 offset $2""", limit, offset,
        )
        slots = await conn.fetch(
            """select cs.id,cs.vendor_id,v.name as vendor_name,cs.service_type,cs.slot_start_time,cs.price_inr,cs.status
               from public.charging_slots cs join public.vendors v on v.id=cs.vendor_id
               order by cs.slot_start_time desc limit $1""", limit,
        )
        hotel_ready = await conn.fetchval("select to_regclass('public.hotel_room_inventory') is not null")
        restaurant_ready = await conn.fetchval("select to_regclass('public.restaurant_menu_items') is not null")
        hotel_rates = []
        menu_prices = []
        if hotel_ready:
            hotel_rates = await conn.fetch(
                """select rt.id as room_type_id,rt.vendor_id,v.name as vendor_name,rt.name as room_type,
                          ri.stay_date,ri.nightly_rate_inr,ri.rooms_available
                   from public.hotel_room_inventory ri join public.hotel_room_types rt on rt.id=ri.room_type_id
                   join public.vendors v on v.id=rt.vendor_id where ri.stay_date >= current_date
                   order by ri.stay_date, v.name limit $1""", limit,
            )
        if restaurant_ready:
            menu_prices = await conn.fetch(
                """select i.id as item_id,i.vendor_id,v.name as vendor_name,i.name as item_name,i.price_inr,i.is_available,i.updated_at
                   from public.restaurant_menu_items i join public.vendors v on v.id=i.vendor_id
                   order by i.updated_at desc limit $1""", limit,
            )
    return success({"service_prices": [dict(row) for row in services], "charging_slot_prices": [dict(row) for row in slots],
                    "hotel_nightly_prices": [dict(row) for row in hotel_rates], "restaurant_menu_prices": [dict(row) for row in menu_prices],
                    "hotel_schema_configured": hotel_ready, "restaurant_schema_configured": restaurant_ready,
                    "limit": limit, "offset": offset})


@router.get("/settings")
async def platform_settings(_admin: Annotated[AdminContext, Depends(require_permission("settings:read"))],
                           database: DatabaseDependency) -> dict[str, Any]:
    settings = get_settings()
    async with database.pool.acquire() as conn:
        commission_settings_configured = await conn.fetchval(
            "select to_regclass('public.platform_commission_settings') is not null"
        )
        commission_ledger_configured = await conn.fetchval(
            "select to_regclass('public.payment_commission_ledger') is not null"
        )
        commission_capture_trigger_configured = await conn.fetchval(
            """select exists (
                 select 1 from information_schema.triggers
                 where trigger_schema='public' and event_object_table='payments'
                   and trigger_name='payments_record_commission'
               )"""
        )
        commission_rate_bps = (
            await conn.fetchval("select rate_bps from public.platform_commission_settings where id=1")
            if commission_settings_configured
            else None
        )
    checkout_credentials_configured = bool(settings.razorpay_key_id and settings.razorpay_key_secret)
    webhook_secret_configured = len(settings.razorpay_webhook_secret) >= 32
    return success({
        "portal_origin": settings.vendor_portal_origin,
        "database": {"configured": bool(settings.database_url)},
        "payment": {"provider": "Razorpay", "public_key_configured": bool(settings.razorpay_key_id),
                    "server_secret_configured": bool(settings.razorpay_key_secret),
                    "webhook_secret_configured": webhook_secret_configured,
                    "mode": settings.razorpay_mode.strip().lower() or "unconfigured",
                    "checkout_ready": checkout_credentials_configured and webhook_secret_configured},
        "commission": {"settings_configured": bool(commission_settings_configured and commission_rate_bps is not None),
                       "ledger_configured": bool(commission_ledger_configured),
                       "capture_trigger_configured": bool(commission_capture_trigger_configured),
                       "rate_bps": int(commission_rate_bps) if commission_rate_bps is not None else None,
                       "scope": "charging_bookings"},
        "vendor_settlement": {"provider": None, "configured": False, "ledger_configured": False,
                              "automatic_transfers_enabled": False,
                              "status": "estimate_only",
                              "reason": "Vendor settlement transfers and payout ledger are not implemented or connected."},
        "geocoding": {"enabled": False, "reason": "No geocoding provider is configured"},
        "redis": {"configured": bool(settings.redis_enabled and settings.redis_url)},
        "editable_platform_config": False,
    })


@router.get("/notifications")
async def admin_notifications(admin: Annotated[AdminContext, Depends(require_permission("notifications:read"))],
                              database: DatabaseDependency,
                              unread_only: bool = False,
                              limit: int = Query(default=50, ge=1, le=100),
                              offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        total = await conn.fetchval("select count(*) from public.notifications where user_id=$1 and (not $2 or read_at is null)", admin.user_id, unread_only)
        unread = await conn.fetchval("select count(*) from public.notifications where user_id=$1 and read_at is null", admin.user_id)
        rows = await conn.fetch(
            """select id,booking_id,type,title,message,read_at,created_at from public.notifications
               where user_id=$1 and (not $2 or read_at is null) order by created_at desc limit $3 offset $4""",
            admin.user_id, unread_only, limit, offset,
        )
    return success({"items": [dict(row) for row in rows], "total": total, "unread": unread, "limit": limit, "offset": offset})


@router.patch("/notifications/{notification_id}/read")
async def admin_mark_notification_read(notification_id: UUID,
                                      admin: Annotated[AdminContext, Depends(require_permission("notifications:read"))],
                                      database: DatabaseDependency) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        row = await conn.fetchrow("update public.notifications set read_at=coalesce(read_at,now()) where id=$1 and user_id=$2 returning id,read_at",
                                  notification_id, admin.user_id)
    if row is None:
        raise ApiError(404, "NOTIFICATION_NOT_FOUND", "Notification was not found")
    return success(dict(row), "Notification marked as read")


@router.post("/notifications/read-all")
async def admin_mark_all_notifications_read(admin: Annotated[AdminContext, Depends(require_permission("notifications:read"))],
                                            database: DatabaseDependency) -> dict[str, Any]:
    async with database.pool.acquire() as conn:
        result = await conn.execute("update public.notifications set read_at=now() where user_id=$1 and read_at is null", admin.user_id)
    return success({"updated": int(result.split()[-1]) if result.startswith("UPDATE ") else 0}, "Notifications marked as read")


def _json(value: dict[str, Any]) -> str:
    import json
    return json.dumps(value, default=str)
