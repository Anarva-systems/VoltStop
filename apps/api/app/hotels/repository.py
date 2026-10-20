"""Transactional hotel inventory and reservation repository."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.errors import ApiError
from app.core.cancellation_policy import POLICY_VERSION, cancellation_quote

HOLD_MINUTES = 15


def _local_today() -> date:
    india_tz = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(india_tz).date()


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _fingerprint(values: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _validate_times(room: Any, check_in_time: time, check_out_time: time) -> None:
    if room.get("is_open_24_hours", True):
        return
    start = room.get("operating_start_time", time(0, 0))
    end = room.get("operating_end_time", time(23, 59))

    def is_open(value: time) -> bool:
        if start <= end:
            return start <= value <= end
        return value >= start or value <= end

    if not is_open(check_in_time) or not is_open(check_out_time):
        hours = f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
        raise ApiError(422, "OUTSIDE_OPERATING_HOURS", f"Choose arrival and departure times during the hotel's daily hours ({hours})")


class HotelRepository:
    def __init__(self, pool: Any):
        self.pool = pool

    async def _expire_pending(self, conn: Any) -> None:
        expired = await conn.fetch(
            """select id, rooms from public.hotel_reservations
               where status='payment_pending' and hold_expires_at <= now()
               order by hold_expires_at limit 100 for update skip locked"""
        )
        for reservation in expired:
            nights = await conn.fetch(
                "select room_type_id,stay_date,rooms from public.hotel_reservation_nights where reservation_id=$1 order by stay_date for update",
                reservation["id"],
            )
            for night in nights:
                await conn.execute(
                    """update public.hotel_room_inventory set rooms_available=least(room_capacity,rooms_available+$3),updated_at=now()
                       where room_type_id=$1 and stay_date=$2""",
                    night["room_type_id"], night["stay_date"], night["rooms"],
                )
            await conn.execute(
                "update public.hotel_reservations set status='expired',updated_at=now() where id=$1",
                reservation["id"],
            )

    async def rooms(self, check_in: date | None, check_out: date | None, guests: int, rooms: int,
                    vendor_id: UUID | None = None, check_in_time: time = time(14, 0),
                    check_out_time: time = time(11, 0)) -> list[dict[str, Any]]:
        if (check_in is None) != (check_out is None):
            raise ApiError(422, "INVALID_STAY", "Provide both check_in and check_out")
        if check_in and (check_in < _local_today() or check_out <= check_in or (check_out - check_in).days > 30):
            raise ApiError(422, "INVALID_STAY", "Stay must be between 1 and 30 nights")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._expire_pending(conn)
                rows = await conn.fetch(
                    """select r.id as room_type_id,r.vendor_id,r.name as room_name,r.description,
                              r.max_guests,r.base_rate_inr,r.total_rooms,r.free_cancellation_hours,
                              r.is_open_24_hours,r.operating_start_time,r.operating_end_time,
                              v.name as vendor_name,v.address,v.lat,v.lng,
                              coalesce((select min(i.nightly_rate_inr) from public.hotel_room_inventory i
                                where i.room_type_id=r.id and i.stay_date >= current_date),r.base_rate_inr) as nightly_rate_inr,
                              case when $1::date is null then null else (
                                select count(*)::int from generate_series($1::date::timestamp,($2::date-1)::timestamp,interval '1 day') as nights(stay_date)
                                join public.hotel_room_inventory i on i.room_type_id=r.id and i.stay_date=nights.stay_date::date
                                where i.rooms_available >= $4) end as available_nights,
                              case when $1::date is null then null else ($2::date-$1::date) end as requested_nights
                       from public.hotel_room_types r join public.vendors v on v.id=r.vendor_id
                       where r.is_active and v.type='hotel' and v.is_active and v.is_verified and r.max_guests * $4 >= $3
                         and ($5::uuid is null or r.vendor_id=$5)
                         and (r.is_open_24_hours or case when r.operating_start_time <= r.operating_end_time
                              then $6::time between r.operating_start_time and r.operating_end_time
                               and $7::time between r.operating_start_time and r.operating_end_time
                              else ($6::time >= r.operating_start_time or $6::time <= r.operating_end_time)
                               and ($7::time >= r.operating_start_time or $7::time <= r.operating_end_time) end)
                         and ($1::date is null or (
                           (select count(*) from generate_series($1::date::timestamp,($2::date-1)::timestamp,interval '1 day') as nights(stay_date)
                            join public.hotel_room_inventory i on i.room_type_id=r.id and i.stay_date=nights.stay_date::date
                            where i.rooms_available >= $4) = ($2::date-$1::date)))
                       order by v.name,r.name limit 200""",
                    check_in, check_out, guests, rooms, vendor_id, check_in_time, check_out_time,
                )
        return [_row(item) or {} for item in rows]

    async def quote(self, room_type_id: UUID, check_in: date, check_out: date, guests: int, rooms: int,
                    check_in_time: time = time(14, 0), check_out_time: time = time(11, 0)) -> dict[str, Any]:
        if check_in < _local_today() or check_out <= check_in or (check_out - check_in).days > 30:
            raise ApiError(422, "INVALID_STAY", "Stay must start today or later and be between 1 and 30 nights")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._expire_pending(conn)
                room = await conn.fetchrow(
                    """select r.id,r.vendor_id,r.name,r.max_guests,r.free_cancellation_hours,
                              r.is_open_24_hours,r.operating_start_time,r.operating_end_time,v.name as vendor_name
                       from public.hotel_room_types r join public.vendors v on v.id=r.vendor_id
                       where r.id=$1 and r.is_active and v.is_active and v.is_verified and v.type='hotel'""",
                    room_type_id,
                )
                if room is None:
                    raise ApiError(404, "ROOM_TYPE_NOT_FOUND", "Available room type was not found")
                _validate_times(room, check_in_time, check_out_time)
                if guests > room["max_guests"] * rooms:
                    raise ApiError(422, "GUEST_LIMIT_EXCEEDED", "Guest count exceeds the selected room capacity")
                inventory = await conn.fetch(
                    """select stay_date,rooms_available,nightly_rate_inr from public.hotel_room_inventory
                       where room_type_id=$1 and stay_date >= $2 and stay_date < $3 order by stay_date""",
                    room_type_id, check_in, check_out,
                )
                nights = (check_out - check_in).days
                if len(inventory) != nights or any(item["rooms_available"] < rooms for item in inventory):
                    raise ApiError(409, "ROOM_UNAVAILABLE", "Room inventory is unavailable for one or more nights")
                amount = sum((Decimal(item["nightly_rate_inr"]) for item in inventory), Decimal("0")) * rooms
                return {"room_type_id": room_type_id, "vendor_id": room["vendor_id"], "vendor_name": room["vendor_name"],
                        "room_name": room["name"], "check_in": check_in, "check_out": check_out,
                        "nights": nights, "guests": guests, "rooms": rooms, "nightly_rates": [
                            {"stay_date": item["stay_date"], "rate_inr": item["nightly_rate_inr"]} for item in inventory],
                        "amount_inr": amount.quantize(Decimal("0.01")), "currency": "INR",
                        "free_cancellation_hours": room["free_cancellation_hours"],
                        "is_open_24_hours": room["is_open_24_hours"],
                        "operating_start_time": room["operating_start_time"],
                        "operating_end_time": room["operating_end_time"],
                        "check_in_time": check_in_time, "check_out_time": check_out_time}

    async def create_reservation(self, customer_id: UUID, values: dict[str, Any], idempotency_key: str) -> tuple[dict[str, Any], bool]:
        values = {"check_in_time": time(14, 0), "check_out_time": time(11, 0), **values}
        fingerprint = _fingerprint({**values, "room_type_id": str(values["room_type_id"])})
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Serialize a caller's idempotency key before checking for a replay.
                await conn.execute("select pg_advisory_xact_lock(hashtext($1),hashtext($2))",
                                   str(customer_id), idempotency_key)
                await self._expire_pending(conn)
                replay = await conn.fetchrow(
                    """select r.*,p.id as payment_id,p.razorpay_order_id,p.amount_inr as payment_amount,
                              p.status as payment_status,p.order_state
                       from public.hotel_reservations r left join public.hotel_reservation_payments p on p.reservation_id=r.id
                       where r.customer_id=$1 and r.idempotency_key=$2 for update of r""",
                    customer_id, idempotency_key,
                )
                if replay:
                    if replay["request_fingerprint"] != fingerprint:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different reservation")
                    return _row(replay) or {}, False

                room = await conn.fetchrow(
                    """select r.vendor_id,r.max_guests,r.free_cancellation_hours,r.is_active,
                              r.is_open_24_hours,r.operating_start_time,r.operating_end_time,
                              v.is_active as vendor_active,v.is_verified,v.type
                       from public.hotel_room_types r join public.vendors v on v.id=r.vendor_id
                       where r.id=$1 for update of r,v""", values["room_type_id"],
                )
                if room is None or room["type"] != "hotel" or not room["is_active"] or not room["vendor_active"] or not room["is_verified"]:
                    raise ApiError(404, "ROOM_TYPE_NOT_FOUND", "Available room type was not found")
                _validate_times(room, values["check_in_time"], values["check_out_time"])
                if values["guests"] > room["max_guests"] * values["rooms"]:
                    raise ApiError(422, "GUEST_LIMIT_EXCEEDED", "Guest count exceeds the selected room capacity")
                inventory = await conn.fetch(
                    """select stay_date,rooms_available,nightly_rate_inr from public.hotel_room_inventory
                       where room_type_id=$1 and stay_date >= $2 and stay_date < $3 order by stay_date for update""",
                    values["room_type_id"], values["check_in"], values["check_out"],
                )
                nights = (values["check_out"] - values["check_in"]).days
                if len(inventory) != nights or any(item["rooms_available"] < values["rooms"] for item in inventory):
                    raise ApiError(409, "ROOM_UNAVAILABLE", "Room inventory is unavailable for one or more nights")
                amount = (sum((Decimal(item["nightly_rate_inr"]) for item in inventory), Decimal("0")) * values["rooms"]).quantize(Decimal("0.01"))
                expected_amount = Decimal(values["expected_amount_inr"]).quantize(Decimal("0.01"))
                if amount != expected_amount:
                    raise ApiError(409, "PRICE_CHANGED", "The server price changed; review a new quote before reserving")
                reservation = await conn.fetchrow(
                    """insert into public.hotel_reservations
                         (customer_id,vendor_id,room_type_id,check_in,check_out,check_in_time,check_out_time,guests,rooms,amount_inr,free_cancellation_hours,status,idempotency_key,request_fingerprint,hold_expires_at)
                       values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'payment_pending',$12,$13,now()+($14::text||' minutes')::interval)
                       returning id,customer_id,vendor_id,room_type_id,check_in,check_out,check_in_time,check_out_time,guests,rooms,amount_inr,free_cancellation_hours,currency,status,hold_expires_at,created_at""",
                    customer_id, room["vendor_id"], values["room_type_id"], values["check_in"], values["check_out"],
                    values["check_in_time"], values["check_out_time"], values["guests"], values["rooms"], amount,
                    room["free_cancellation_hours"], idempotency_key, fingerprint, HOLD_MINUTES,
                )
                payment_id = await conn.fetchval(
                    "insert into public.hotel_reservation_payments(reservation_id,amount_inr) values($1,$2) returning id",
                    reservation["id"], amount,
                )
                for item in inventory:
                    updated = await conn.fetchval(
                        """update public.hotel_room_inventory set rooms_available=rooms_available-$3,updated_at=now()
                           where room_type_id=$1 and stay_date=$2 and rooms_available >= $3 returning rooms_available""",
                        values["room_type_id"], item["stay_date"], values["rooms"],
                    )
                    if updated is None:
                        raise ApiError(409, "ROOM_UNAVAILABLE", "Room inventory changed; please choose another stay")
                    await conn.execute(
                        """insert into public.hotel_reservation_nights(reservation_id,room_type_id,stay_date,rooms,nightly_rate_inr)
                           values($1,$2,$3,$4,$5)""",
                        reservation["id"], values["room_type_id"], item["stay_date"], values["rooms"], item["nightly_rate_inr"],
                    )
                result = _row(reservation) or {}
                result.update({"payment_id": payment_id, "payment_status": "pending", "order_state": "creating"})
        return result, True

    async def attach_order(self, payment_id: UUID, order_id: str) -> None:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "update public.hotel_reservation_payments set razorpay_order_id=$2,order_state='ready',updated_at=now() where id=$1 and order_state='creating' and razorpay_order_id is null",
                payment_id, order_id,
            )
            if result.endswith(" 0"):
                raise ApiError(409, "PAYMENT_ORDER_STATE_CHANGED", "Reservation payment is no longer available")

    async def mark_order_unknown(self, payment_id: UUID) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "update public.hotel_reservation_payments set order_state='reconciliation_required',updated_at=now() where id=$1 and order_state='creating'",
                payment_id,
            )

    async def reservation(self, customer_id: UUID, reservation_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._expire_pending(conn)
                row = await conn.fetchrow(
            """select r.id,r.customer_id,r.vendor_id,r.room_type_id,r.check_in,r.check_out,r.check_in_time,r.check_out_time,r.guests,r.rooms,
                          r.amount_inr,r.currency,r.status,r.free_cancellation_hours,r.cancellation_fee_inr,r.refund_amount_inr,
                          r.cancellation_policy_version,r.cancelled_at,r.hold_expires_at,r.created_at,r.updated_at,
                          v.name as vendor_name,v.address as vendor_address,v.lat as vendor_lat,v.lng as vendor_lng,
                          rt.name as room_name,rt.description as room_description,
                          rt.max_guests,p.razorpay_order_id,p.razorpay_payment_id,p.amount_inr as payment_amount,
                          p.status as payment_status,p.webhook_verified,p.order_state,
                          (select f.status from public.hotel_refunds f where f.reservation_id=r.id order by f.created_at desc limit 1) as refund_status
                   from public.hotel_reservations r join public.vendors v on v.id=r.vendor_id
                   join public.hotel_room_types rt on rt.id=r.room_type_id
                   left join public.hotel_reservation_payments p on p.reservation_id=r.id
                   where r.id=$1 and r.customer_id=$2""", reservation_id, customer_id)
            if row is None:
                exists = await conn.fetchval("select exists(select 1 from public.hotel_reservations where id=$1)", reservation_id)
                if exists:
                    raise ApiError(403, "FORBIDDEN", "You cannot access this reservation")
                return None
            result = _row(row) or {}
            result["nightly_rates"] = [_row(item) for item in await conn.fetch(
                "select stay_date,rooms,nightly_rate_inr from public.hotel_reservation_nights where reservation_id=$1 order by stay_date", reservation_id)]
            return result

    async def reservations(self, customer_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._expire_pending(conn)
                rows = await conn.fetch(
                    """select r.id,r.vendor_id,r.room_type_id,r.check_in,r.check_out,r.check_in_time,r.check_out_time,r.guests,r.rooms,r.amount_inr,r.currency,r.status,
                          r.cancellation_fee_inr,r.refund_amount_inr,r.cancellation_policy_version,r.cancelled_at,
                          r.hold_expires_at,r.created_at,v.name as vendor_name,v.address as vendor_address,
                          v.lat as vendor_lat,v.lng as vendor_lng,rt.name as room_name,p.status as payment_status,
                          (select f.status from public.hotel_refunds f where f.reservation_id=r.id order by f.created_at desc limit 1) as refund_status
                   from public.hotel_reservations r join public.vendors v on v.id=r.vendor_id
                   join public.hotel_room_types rt on rt.id=r.room_type_id
                   left join public.hotel_reservation_payments p on p.reservation_id=r.id
                   where r.customer_id=$1 order by r.created_at desc limit 100""", customer_id)
        return [_row(item) or {} for item in rows]

    async def cancellation_quote(self, customer_id: UUID, reservation_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """select r.id,r.customer_id,r.check_in,r.check_in_time,r.amount_inr,r.status,
                          p.status as payment_status,p.webhook_verified,p.razorpay_payment_id
                   from public.hotel_reservations r left join public.hotel_reservation_payments p on p.reservation_id=r.id
                   where r.id=$1""", reservation_id)
        if row is None:
            return None
        if row["customer_id"] != customer_id:
            raise ApiError(403, "FORBIDDEN", "You cannot access this reservation")
        if row["status"] not in ("payment_pending", "confirmed"):
            raise ApiError(409, "RESERVATION_NOT_CANCELLABLE", "Reservation is not cancellable in its current state")
        is_paid = row["payment_status"] == "captured" and row["webhook_verified"]
        if row["payment_status"] in ("captured", "authorized") and not (row["payment_status"] == "captured" and row["webhook_verified"]):
            raise ApiError(409, "PAYMENT_NOT_VERIFIED", "Cancellation is blocked until payment is reconciled")
        if row["status"] == "confirmed" and not is_paid:
            raise ApiError(409, "PAYMENT_NOT_VERIFIED", "Cancellation is blocked until payment is verified")
        if is_paid and not row["razorpay_payment_id"]:
            raise ApiError(409, "PAYMENT_NOT_VERIFIED", "The captured payment is missing its provider reference")
        if not is_paid:
            return {"policy_version": POLICY_VERSION, "tier": "payment_pending", "hours_before_start": None,
                    "captured_amount_inr": Decimal("0.00"), "customer_refund_inr": Decimal("0.00"),
                    "retained_amount_inr": Decimal("0.00"), "refund_percent": 0,
                    "gateway_fee_deduction_inr": Decimal("0.00")}
        india_tz = timezone(timedelta(hours=5, minutes=30))
        service_start = datetime.combine(row["check_in"], row["check_in_time"]).replace(tzinfo=india_tz)
        return cancellation_quote(Decimal(row["amount_inr"]), service_start)

    async def cancel(self, customer_id: UUID, reservation_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                reservation = await conn.fetchrow(
                    """select r.* from public.hotel_reservations r
                       join public.hotel_room_types rt on rt.id=r.room_type_id where r.id=$1 for update of r""", reservation_id)
                if reservation is None:
                    return None
                if reservation["customer_id"] != customer_id:
                    raise ApiError(403, "FORBIDDEN", "You cannot cancel this reservation")
                if reservation["status"] in ("cancelled", "refund_pending", "refund_failed", "refund_partial", "refunded") and reservation["cancelled_at"] is not None:
                    return _row(reservation)
                if reservation["status"] not in ("payment_pending", "confirmed"):
                    raise ApiError(409, "RESERVATION_NOT_CANCELLABLE", "Reservation is not cancellable in its current state")
                payment = await conn.fetchrow(
                    "select * from public.hotel_reservation_payments where reservation_id=$1 for update", reservation_id)
                is_paid = bool(payment and payment["status"] == "captured" and payment["webhook_verified"])
                if payment and payment["status"] in ("captured", "authorized") and not is_paid:
                    raise ApiError(409, "PAYMENT_NOT_VERIFIED", "Cancellation is blocked until payment is reconciled")
                if reservation["status"] == "confirmed" and not is_paid:
                    raise ApiError(409, "PAYMENT_NOT_VERIFIED", "Cancellation is blocked until payment is verified")
                if is_paid and not payment["razorpay_payment_id"]:
                    raise ApiError(409, "PAYMENT_NOT_VERIFIED", "The captured payment is missing its provider reference")
                if reservation["status"] == "confirmed":
                    active_refund = await conn.fetchval(
                        """select exists(select 1 from public.hotel_refunds where payment_id=$1
                           and status not in ('failed','rejected'))""", payment["id"])
                    if active_refund:
                        raise ApiError(409, "REFUND_ALREADY_IN_PROGRESS", "A refund for this reservation is already in progress")
                    india_tz = timezone(timedelta(hours=5, minutes=30))
                    service_start = datetime.combine(reservation["check_in"], reservation["check_in_time"]).replace(tzinfo=india_tz)
                    quote = cancellation_quote(Decimal(reservation["amount_inr"]), service_start)
                else:
                    quote = {"policy_version": POLICY_VERSION, "customer_refund_inr": Decimal("0.00"),
                             "retained_amount_inr": Decimal("0.00"), "tier": "payment_pending"}
                nights = await conn.fetch(
                    "select room_type_id,stay_date,rooms from public.hotel_reservation_nights where reservation_id=$1 order by stay_date for update", reservation_id)
                started = quote["tier"] == "service_started"
                local_today = _local_today()
                for night in nights:
                    if started and night["stay_date"] <= local_today:
                        continue
                    await conn.execute(
                        """update public.hotel_room_inventory set rooms_available=least(room_capacity,rooms_available+$3),updated_at=now()
                           where room_type_id=$1 and stay_date=$2""", night["room_type_id"], night["stay_date"], night["rooms"])
                refund_amount = Decimal(quote["customer_refund_inr"])
                fee_amount = Decimal(quote["retained_amount_inr"])
                if is_paid and refund_amount > 0:
                    await conn.execute(
                        """insert into public.hotel_refunds(reservation_id,payment_id,amount_inr,reason,idempotency_key,requested_by)
                           values($1,$2,$3,'Customer cancellation','cancel:'||$1::text,$4) on conflict(idempotency_key) do nothing""",
                        reservation_id, payment["id"], refund_amount, customer_id)
                    status = "refund_pending"
                else:
                    if payment:
                        await conn.execute("update public.hotel_reservation_payments set status='failed',updated_at=now() where id=$1 and status='pending'", payment["id"])
                    status = "cancelled"
                await conn.execute(
                    """update public.hotel_reservations set status=$2,cancellation_fee_inr=$3,
                       refund_amount_inr=$4,cancellation_policy_version=$5,cancelled_at=now(),updated_at=now() where id=$1""",
                    reservation_id, status, fee_amount, refund_amount, quote["policy_version"])
        return await self.reservation(customer_id, reservation_id)

    async def vendor_rooms(self, owner_id: UUID, vendor_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select r.* from public.hotel_room_types r join public.vendors v on v.id=r.vendor_id
                   where r.vendor_id=$1 and v.owner_id=$2 order by r.created_at desc""", vendor_id, owner_id)
        return [_row(item) or {} for item in rows]

    async def create_room_type(self, owner_id: UUID, vendor_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """insert into public.hotel_room_types(vendor_id,name,description,max_guests,base_rate_inr,total_rooms,free_cancellation_hours,is_active,is_open_24_hours,operating_start_time,operating_end_time)
                   select $1,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12 where exists(select 1 from public.vendors where id=$1 and owner_id=$2 and type='hotel')
                   returning *""", vendor_id, owner_id, values["name"].strip(), values.get("description"), values["max_guests"],
                values["base_rate_inr"], values["total_rooms"], values["free_cancellation_hours"], values["is_active"],
                values["is_open_24_hours"], values["operating_start_time"], values["operating_end_time"])
        if row is None:
            raise ApiError(404, "HOTEL_VENDOR_NOT_FOUND", "Hotel vendor profile was not found")
        return _row(row) or {}

    async def update_room_type(self, owner_id: UUID, vendor_id: UUID, room_type_id: UUID, updates: dict[str, Any]) -> dict[str, Any] | None:
        selected = [(key, value) for key, value in updates.items() if key in {
            "name", "description", "max_guests", "base_rate_inr", "total_rooms", "free_cancellation_hours", "is_active",
            "is_open_24_hours", "operating_start_time", "operating_end_time"}]
        if not selected:
            raise ApiError(422, "EMPTY_PATCH", "Provide at least one room field to update")
        columns = ",".join(f"{key}=${index}" for index, (key, _) in enumerate(selected, 1))
        args = [value for _, value in selected] + [room_type_id, vendor_id, owner_id]
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if any(key in updates for key in ("is_open_24_hours", "operating_start_time", "operating_end_time")):
                    current_hours = await conn.fetchrow(
                        """select r.is_open_24_hours,r.operating_start_time,r.operating_end_time
                           from public.hotel_room_types r join public.vendors v on v.id=r.vendor_id
                           where r.id=$1 and r.vendor_id=$2 and v.owner_id=$3 for update of r""",
                        room_type_id, vendor_id, owner_id)
                    if current_hours is None:
                        return None
                    is_open = updates.get("is_open_24_hours", current_hours["is_open_24_hours"])
                    start = updates.get("operating_start_time", current_hours["operating_start_time"])
                    end = updates.get("operating_end_time", current_hours["operating_end_time"])
                    if not is_open and start == end:
                        raise ApiError(422, "INVALID_OPERATING_HOURS", "Opening and closing times must differ unless the room is open 24 hours")
                if "total_rooms" in updates:
                    occupied = await conn.fetchval(
                        """select exists(select 1 from public.hotel_room_inventory where room_type_id=$1
                           and room_capacity > $2) or exists(select 1 from public.hotel_room_inventory where room_type_id=$1
                           and room_capacity-rooms_available > $2)""", room_type_id, updates["total_rooms"])
                    if occupied:
                        raise ApiError(409,"ROOM_CAPACITY_IN_USE","Total rooms cannot be reduced below published or reserved inventory")
                row = await conn.fetchrow(
                    f"""update public.hotel_room_types r set {columns},updated_at=now() from public.vendors v
                       where r.id=${len(args)-2} and r.vendor_id=${len(args)-1} and v.id=r.vendor_id and v.owner_id=${len(args)}
                       returning r.*""", *args)
        return _row(row)

    async def inventory(self, owner_id: UUID, vendor_id: UUID, room_type_id: UUID, start: date, end: date) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select i.* from public.hotel_room_inventory i join public.hotel_room_types r on r.id=i.room_type_id
                   join public.vendors v on v.id=r.vendor_id where i.room_type_id=$1 and r.vendor_id=$2 and v.owner_id=$3
                     and i.stay_date >= $4 and i.stay_date < $5 order by i.stay_date""", room_type_id,vendor_id,owner_id,start,end)
        return [_row(item) or {} for item in rows]

    async def upsert_inventory(self, owner_id: UUID, vendor_id: UUID, room_type_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                room = await conn.fetchrow(
                    """select r.total_rooms from public.hotel_room_types r join public.vendors v on v.id=r.vendor_id
                       where r.id=$1 and r.vendor_id=$2 and v.owner_id=$3 for update of r""", room_type_id,vendor_id,owner_id)
                if room is None:
                    raise ApiError(404, "ROOM_TYPE_NOT_FOUND", "Room type was not found")
                capacity = values.get("room_capacity", room["total_rooms"])
                if capacity > room["total_rooms"] or values["rooms_available"] > capacity:
                    raise ApiError(422, "INVALID_INVENTORY", "Nightly inventory cannot exceed the room type capacity")
                existing = await conn.fetchrow(
                    "select room_capacity,rooms_available from public.hotel_room_inventory where room_type_id=$1 and stay_date=$2 for update",
                    room_type_id,values["stay_date"])
                booked_rooms = (existing["room_capacity"] - existing["rooms_available"]) if existing else 0
                if capacity < booked_rooms or values["rooms_available"] > capacity - booked_rooms:
                    raise ApiError(409, "INVENTORY_BELOW_RESERVATIONS", "Nightly inventory cannot be reduced below already reserved rooms")
                row = await conn.fetchrow(
                    """insert into public.hotel_room_inventory(room_type_id,stay_date,room_capacity,rooms_available,nightly_rate_inr)
                       values($1,$2,$3,$4,$5) on conflict(room_type_id,stay_date) do update set
                       room_capacity=excluded.room_capacity,rooms_available=excluded.rooms_available,
                       nightly_rate_inr=excluded.nightly_rate_inr,updated_at=now() returning *""",
                    room_type_id,values["stay_date"],capacity,values["rooms_available"],values["nightly_rate_inr"])
        return _row(row) or {}

    async def vendor_reservations(self, owner_id: UUID, vendor_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """select r.id,r.customer_id,r.room_type_id,r.check_in,r.check_out,r.check_in_time,r.check_out_time,r.guests,r.rooms,r.amount_inr,r.currency,r.status,
                          r.cancellation_fee_inr,r.refund_amount_inr,r.cancellation_policy_version,r.cancelled_at,r.created_at,
                          rt.name as room_name,p.status as payment_status,p.webhook_verified,pr.name as customer_name,pr.phone as customer_phone,
                          (select f.status from public.hotel_refunds f where f.reservation_id=r.id order by f.created_at desc limit 1) as refund_status
                   from public.hotel_reservations r join public.vendors v on v.id=r.vendor_id
                   join public.hotel_room_types rt on rt.id=r.room_type_id join public.profiles pr on pr.id=r.customer_id
                   left join public.hotel_reservation_payments p on p.reservation_id=r.id
                   where r.vendor_id=$1 and v.owner_id=$2 order by r.created_at desc limit 250""", vendor_id,owner_id)
        return [_row(item) or {} for item in rows]

    async def admin_refunds(self, status: str | None, limit: int, offset: int) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            total = await conn.fetchval("select count(*) from public.hotel_refunds where $1::text is null or status=$1", status)
            rows = await conn.fetch(
                """select f.*,r.customer_id,r.vendor_id,r.check_in,r.check_out,r.status as reservation_status,
                          r.amount_inr as reservation_amount,v.name as vendor_name,rt.name as room_name,
                          p.razorpay_payment_id,p.status as payment_status,p.webhook_verified
                   from public.hotel_refunds f join public.hotel_reservations r on r.id=f.reservation_id
                   join public.vendors v on v.id=r.vendor_id join public.hotel_room_types rt on rt.id=r.room_type_id
                   join public.hotel_reservation_payments p on p.id=f.payment_id
                   where $1::text is null or f.status=$1 order by f.created_at desc limit $2 offset $3""",
                status, limit, offset)
        return {"items": [_row(item) or {} for item in rows], "total": total, "limit": limit, "offset": offset}

    async def approve_refund(self, actor_id: UUID, refund_id: UUID, reason: str) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """select f.*,p.razorpay_payment_id,p.amount_inr as payment_amount,p.status as payment_status,p.webhook_verified
                       from public.hotel_refunds f join public.hotel_reservation_payments p on p.id=f.payment_id
                       where f.id=$1 for update of f,p""", refund_id)
                if row is None:
                    raise ApiError(404,"HOTEL_REFUND_NOT_FOUND","Hotel refund request was not found")
                if row["status"] == "approved":
                    return _row(row) or {}
                if row["status"] != "requested":
                    raise ApiError(409,"HOTEL_REFUND_NOT_REQUESTED","Hotel refund request is no longer awaiting approval")
                if row["payment_status"] != "captured" or not row["webhook_verified"] or not row["razorpay_payment_id"]:
                    raise ApiError(409,"HOTEL_PAYMENT_NOT_VERIFIED","Only a verified captured payment can be refunded")
                reserved = await conn.fetchval(
                    """select coalesce(sum(amount_inr),0) from public.hotel_refunds where payment_id=$1
                       and status not in ('failed','rejected')""",row["payment_id"])
                if Decimal(reserved) > Decimal(row["payment_amount"]):
                    raise ApiError(409,"HOTEL_REFUND_LIMIT_EXCEEDED","Refund total exceeds the captured payment")
                updated = await conn.fetchrow(
                    """update public.hotel_refunds set status='approved',approved_by=$2,provider_error=$3,updated_at=now()
                       where id=$1 returning *""",refund_id,actor_id,reason[:500])
        return _row(updated) or {}

    async def claim_refund(self, refund_id: UUID) -> tuple[dict[str, Any], bool]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """select f.*,p.razorpay_payment_id,p.status as payment_status,p.webhook_verified
                       from public.hotel_refunds f join public.hotel_reservation_payments p on p.id=f.payment_id
                       where f.id=$1 for update of f,p""",refund_id)
                if row is None:
                    raise ApiError(404,"HOTEL_REFUND_NOT_FOUND","Hotel refund request was not found")
                if row["status"] != "approved":
                    return _row(row) or {},False
                if row["payment_status"]!="captured" or not row["webhook_verified"] or not row["razorpay_payment_id"]:
                    raise ApiError(409,"HOTEL_PAYMENT_NOT_VERIFIED","Refund payment is not verified")
                await conn.execute("update public.hotel_refunds set status='processing',updated_at=now() where id=$1",refund_id)
                return _row(row) or {},True

    async def finish_refund(self, refund_id: UUID, provider_id: str | None, provider_status: str,
                            local_status: str, error: str | None = None) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row=await conn.fetchrow(
                """update public.hotel_refunds set razorpay_refund_id=coalesce($2,razorpay_refund_id),
                   provider_status=coalesce(provider_status,$3),
                   status=case when status in ('completed','failed','rejected') then status else $4 end,
                   provider_error=$5,updated_at=now() where id=$1 returning *""",
                refund_id,provider_id,provider_status,local_status,error)
            if row is not None and local_status == "failed":
                await conn.execute("update public.hotel_reservations set status='refund_failed',updated_at=now() where id=(select reservation_id from public.hotel_refunds where id=$1) and status='refund_pending'",refund_id)
            elif row is not None and local_status == "completed":
                state = await conn.fetchrow(
                    """select f.reservation_id,f.payment_id,p.amount_inr,
                              (select coalesce(sum(x.amount_inr),0) from public.hotel_refunds x
                               where x.payment_id=f.payment_id and x.status='completed') as refunded
                       from public.hotel_refunds f join public.hotel_reservation_payments p on p.id=f.payment_id
                       where f.id=$1""", refund_id)
                if state is not None:
                    fully_refunded = Decimal(state["refunded"]) >= Decimal(state["amount_inr"])
                    await conn.execute(
                        "update public.hotel_reservations set status=$2,updated_at=now() where id=$1 and status='refund_pending'",
                        state["reservation_id"], "refunded" if fully_refunded else "refund_partial")
                    if fully_refunded:
                        await conn.execute(
                            "update public.hotel_reservation_payments set status='refunded',updated_at=now() where id=$1",
                            state["payment_id"])
        if row is None:
            raise ApiError(404,"HOTEL_REFUND_NOT_FOUND","Hotel refund request was not found")
        return _row(row) or {}

    async def reject_refund(self, actor_id: UUID, refund_id: UUID, reason: str) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("select * from public.hotel_refunds where id=$1 for update",refund_id)
                if row is None:
                    raise ApiError(404,"HOTEL_REFUND_NOT_FOUND","Hotel refund request was not found")
                if row["status"] != "requested":
                    raise ApiError(409,"HOTEL_REFUND_NOT_REQUESTED","Only a requested hotel refund can be rejected")
                updated = await conn.fetchrow(
                    "update public.hotel_refunds set status='rejected',approved_by=$2,provider_error=$3,updated_at=now() where id=$1 returning *",
                    refund_id,actor_id,reason[:500])
                await conn.execute("update public.hotel_reservations set status='cancelled',updated_at=now() where id=$1 and status='refund_pending'",row["reservation_id"])
        return _row(updated) or {}

    async def process_payment_webhook(self, order_id: str, payment_id: str, amount_paise: int, currency: str, captured: bool) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                payment = await conn.fetchrow("select * from public.hotel_reservation_payments where razorpay_order_id=$1", order_id)
                if payment is None:
                    return False
                reservation = await conn.fetchrow("select * from public.hotel_reservations where id=$1 for update",payment["reservation_id"])
                row = await conn.fetchrow("select * from public.hotel_reservation_payments where id=$1 for update",payment["id"])
                if reservation is None or row is None or row["razorpay_order_id"] != order_id:
                    return False
                if row["razorpay_payment_id"] not in (None,payment_id) or row["currency"].strip().upper()!=currency.strip().upper():
                    raise ApiError(400,"PAYMENT_WEBHOOK_REJECTED","Webhook payment could not be verified")
                if int(Decimal(row["amount_inr"])*100) != amount_paise:
                    raise ApiError(400,"PAYMENT_AMOUNT_MISMATCH","Webhook payment could not be verified")
                duplicate = await conn.fetchval("select exists(select 1 from public.hotel_reservation_payments where razorpay_payment_id=$1 and id<>$2)",payment_id,row["id"])
                if duplicate:
                    raise ApiError(400,"PAYMENT_WEBHOOK_REJECTED","Webhook payment could not be verified")
                if row["status"] in ("captured","refunded") or (row["status"]=="failed" and not captured):
                    if row["razorpay_payment_id"] is None:
                        raise ApiError(400,"PAYMENT_WEBHOOK_REJECTED","Webhook payment could not be verified")
                    return True
                await conn.execute("update public.hotel_reservation_payments set status=$2,webhook_verified=true,razorpay_payment_id=$3,updated_at=now() where id=$1",
                    row["id"],"captured" if captured else "failed",payment_id)
                late_capture = captured and (reservation["status"] in ("expired","cancelled") or
                    (reservation["status"] == "payment_pending" and reservation["hold_expires_at"] <= datetime.now(timezone.utc)))
                if captured and reservation["status"]=="payment_pending" and not late_capture:
                    await conn.execute("update public.hotel_reservations set status='confirmed',updated_at=now() where id=$1",reservation["id"])
                elif late_capture:
                    if reservation["status"] == "payment_pending":
                        nights=await conn.fetch("select room_type_id,stay_date,rooms from public.hotel_reservation_nights where reservation_id=$1 order by stay_date for update",reservation["id"])
                        for night in nights:
                            await conn.execute("update public.hotel_room_inventory set rooms_available=least(room_capacity,rooms_available+$3),updated_at=now() where room_type_id=$1 and stay_date=$2",
                                night["room_type_id"],night["stay_date"],night["rooms"])
                    await conn.execute("update public.hotel_reservations set status='refund_pending',updated_at=now() where id=$1",reservation["id"])
                    await conn.execute(
                        """insert into public.hotel_refunds(reservation_id,payment_id,amount_inr,reason,idempotency_key,requested_by)
                           values($1,$2,$3,'Late payment capture after reservation hold ended','late-capture:'||$1::text,$4)
                           on conflict(idempotency_key) do nothing""",reservation["id"],row["id"],row["amount_inr"],reservation["customer_id"])
                elif not captured and reservation["status"]=="payment_pending":
                    nights=await conn.fetch("select room_type_id,stay_date,rooms from public.hotel_reservation_nights where reservation_id=$1 order by stay_date for update",reservation["id"])
                    for night in nights:
                        await conn.execute("update public.hotel_room_inventory set rooms_available=least(room_capacity,rooms_available+$3),updated_at=now() where room_type_id=$1 and stay_date=$2",
                            night["room_type_id"],night["stay_date"],night["rooms"])
                    await conn.execute("update public.hotel_reservations set status='expired',updated_at=now() where id=$1",reservation["id"])
                return True

    async def process_refund_webhook(self, refund_id: str, payment_id: str, amount_paise: int, currency: str, provider_status: str, local_refund_id: str | None) -> bool:
        if not local_refund_id:
            return False
        try:
            parsed_refund_id = UUID(local_refund_id)
        except (ValueError, TypeError):
            return False
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                refund = await conn.fetchrow("select * from public.hotel_refunds where id=$1 for update",parsed_refund_id)
                if refund is None:
                    return False
                payment = await conn.fetchrow("select * from public.hotel_reservation_payments where id=$1 for update",refund["payment_id"])
                if payment is None or payment["razorpay_payment_id"] != payment_id or payment["currency"].strip().upper()!=currency.strip().upper() or int(Decimal(refund["amount_inr"])*100)!=amount_paise:
                    raise ApiError(400,"REFUND_WEBHOOK_REJECTED","Refund event could not be verified")
                if refund["razorpay_refund_id"] not in (None,refund_id):
                    raise ApiError(400,"REFUND_WEBHOOK_REJECTED","Refund event could not be verified")
                if refund["status"] in ("completed","failed","rejected"):
                    return True
                status = "completed" if provider_status in ("processed","completed") else "failed" if provider_status=="failed" else "processing"
                await conn.execute("update public.hotel_refunds set razorpay_refund_id=$2,provider_status=$3,status=$4,updated_at=now() where id=$1",
                    refund["id"],refund_id,provider_status,status)
                if status=="completed":
                    total=await conn.fetchval("select coalesce(sum(amount_inr),0) from public.hotel_refunds where payment_id=$1 and status='completed'",payment["id"])
                    if Decimal(total)>=Decimal(payment["amount_inr"]):
                        await conn.execute("update public.hotel_reservation_payments set status='refunded',updated_at=now() where id=$1",payment["id"])
                        await conn.execute("update public.hotel_reservations set status='refunded',updated_at=now() where id=$1",refund["reservation_id"])
                    else:
                        await conn.execute("update public.hotel_reservations set status='refund_partial',updated_at=now() where id=$1 and status='refund_pending'",refund["reservation_id"])
                elif status=="failed":
                    await conn.execute("update public.hotel_reservations set status='refund_failed',updated_at=now() where id=$1 and status='refund_pending'",refund["reservation_id"])
                return True
