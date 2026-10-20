import json

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.core.errors import ApiError


def _json_value(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _record_value(record: asyncpg.Record | dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    result = dict(record)
    for key in ("vendor", "services", "available_slots", "availability", "timeline", "route_plan"):
        if key in result:
            result[key] = _json_value(result[key])
    return result


class Database:
    """Async PostgreSQL repository. User-scoped reads always include the JWT subject."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def user_owns_payment_order(self, order_id: str, user_id: UUID) -> bool:
        async with self.pool.acquire() as connection:
            return bool(await connection.fetchval(
                """select
                     exists(select 1 from public.payments p
                            join public.bookings b on b.payment_id=p.id
                            where p.razorpay_order_id=$1 and b.user_id=$2)
                     or exists(select 1 from public.hotel_reservation_payments p
                               join public.hotel_reservations r on r.id=p.reservation_id
                               where p.razorpay_order_id=$1 and r.customer_id=$2)
                     or exists(select 1 from public.restaurant_order_payments p
                               join public.restaurant_orders o on o.id=p.order_id
                               where p.razorpay_order_id=$1 and o.customer_id=$2)""",
                order_id, user_id,
            ))

    async def hotel_payment_for_reservation(self, reservation_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select id,reservation_id,razorpay_order_id,razorpay_payment_id,amount_inr,currency,status,
                          webhook_verified,order_state from public.hotel_reservation_payments where reservation_id=$1""",
                reservation_id,
            )
        return _record_value(row)

    async def process_hotel_payment_webhook(self, order_id: str, payment_id: str, amount_paise: int,
                                            currency: str, captured: bool) -> bool:
        from app.hotels.repository import HotelRepository
        return await HotelRepository(self.pool).process_payment_webhook(order_id, payment_id, amount_paise, currency, captured)

    async def process_hotel_refund_webhook(self, refund_id: str, payment_id: str, amount_paise: int,
                                           currency: str, provider_status: str, local_refund_id: str | None) -> bool:
        from app.hotels.repository import HotelRepository
        return await HotelRepository(self.pool).process_refund_webhook(
            refund_id, payment_id, amount_paise, currency, provider_status, local_refund_id
        )

    async def profile(self, user_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select id, phone, name, car_model, battery_kwh,
                          default_efficiency_km_per_kwh, current_soc, created_at, updated_at
                   from public.profiles where id = $1""",
                user_id,
            )
        return _record_value(row)

    async def patch_profile(self, user_id: UUID, updates: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "name": "name",
            "car_model": "car_model",
            "battery_kwh": "battery_kwh",
            "default_efficiency_km_per_kwh": "default_efficiency_km_per_kwh",
            "current_soc": "current_soc",
        }
        selected = [(allowed[key], value) for key, value in updates.items() if key in allowed]
        if not selected:
            return await self.profile(user_id)
        set_parts = [f"{column} = ${index}" for index, (column, _) in enumerate(selected, start=1)]
        values = [value for _, value in selected]
        values.append(user_id)
        sql = (
            "update public.profiles set " + ", ".join(set_parts)
            + f" where id = ${len(values)} returning id, phone, name, car_model, battery_kwh, "
              "default_efficiency_km_per_kwh, current_soc, created_at, updated_at"
        )
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(sql, *values)
        return _record_value(row)

    async def driver_vehicles(self, user_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select id,user_id,make,model,vehicle_type,battery_kwh,efficiency_km_per_kwh,
                          current_soc,connector_compatibility,is_default,created_at,updated_at
                   from public.driver_vehicles where user_id=$1
                   order by is_default desc,created_at,id""", user_id,
            )
        return [_record_value(row) or {} for row in rows]

    async def driver_vehicle(self, user_id: UUID, vehicle_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select id,user_id,make,model,vehicle_type,battery_kwh,efficiency_km_per_kwh,
                          current_soc,connector_compatibility,is_default,created_at,updated_at
                   from public.driver_vehicles where user_id=$1 and id=$2""", user_id, vehicle_id,
            )
        return _record_value(row)

    async def create_driver_vehicle(self, user_id: UUID, values: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.fetchrow("select id from public.profiles where id=$1 for update", user_id)
                replay = await connection.fetchrow(
                    "select * from public.driver_vehicles where user_id=$1 and idempotency_key=$2",
                    user_id, idempotency_key,
                )
                if replay is not None:
                    comparable = (replay["make"], replay["model"], replay["vehicle_type"],
                                  float(replay["battery_kwh"]), float(replay["efficiency_km_per_kwh"]),
                                  float(replay["current_soc"]) if replay["current_soc"] is not None else None,
                                  list(replay["connector_compatibility"] or []))
                    requested = (values["make"], values["model"], values["vehicle_type"],
                                 float(values["battery_kwh"]), float(values["efficiency_km_per_kwh"]),
                                 values.get("current_soc"), values.get("connector_compatibility", []))
                    if comparable != requested:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different vehicle")
                    row = replay
                else:
                    has_default = await connection.fetchval(
                        "select exists(select 1 from public.driver_vehicles where user_id=$1 and is_default)", user_id
                    )
                    make_default = bool(values.get("is_default")) or not has_default
                    if make_default:
                        await connection.execute("update public.driver_vehicles set is_default=false where user_id=$1", user_id)
                    row = await connection.fetchrow(
                        """insert into public.driver_vehicles
                             (user_id,make,model,vehicle_type,battery_kwh,efficiency_km_per_kwh,current_soc,
                              connector_compatibility,is_default,idempotency_key)
                           values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                           returning id,user_id,make,model,vehicle_type,battery_kwh,efficiency_km_per_kwh,
                                     current_soc,connector_compatibility,is_default,created_at,updated_at""",
                        user_id, values["make"], values["model"], values["vehicle_type"], Decimal(str(values["battery_kwh"])),
                        Decimal(str(values["efficiency_km_per_kwh"])), Decimal(str(values["current_soc"])) if values.get("current_soc") is not None else None,
                        values.get("connector_compatibility", []), make_default, idempotency_key,
                    )
                    if make_default:
                        await connection.execute(
                            """update public.profiles set car_model=$2,battery_kwh=$3,
                                      default_efficiency_km_per_kwh=$4,current_soc=$5,updated_at=now() where id=$1""",
                            user_id, f"{values['make']} {values['model']}", Decimal(str(values["battery_kwh"])),
                            Decimal(str(values["efficiency_km_per_kwh"])), Decimal(str(values["current_soc"])) if values.get("current_soc") is not None else None,
                        )
        return _record_value(row) or {}

    async def patch_driver_vehicle(self, user_id: UUID, vehicle_id: UUID, changes: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"make", "model", "vehicle_type", "battery_kwh", "efficiency_km_per_kwh", "current_soc", "connector_compatibility"}
        updates = {key: value for key, value in changes.items() if key in allowed}
        for key in ("battery_kwh", "efficiency_km_per_kwh", "current_soc"):
            if key in updates and updates[key] is not None:
                updates[key] = Decimal(str(updates[key]))
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.fetchrow("select id from public.profiles where id=$1 for update", user_id)
                current = await connection.fetchrow(
                    "select id,is_default from public.driver_vehicles where user_id=$1 and id=$2 for update",
                    user_id, vehicle_id,
                )
                if current is None:
                    return None
                if changes.get("is_default") is True:
                    await connection.execute("update public.driver_vehicles set is_default=false where user_id=$1", user_id)
                elif changes.get("is_default") is False and current["is_default"]:
                    other = await connection.fetchval(
                        "select exists(select 1 from public.driver_vehicles where user_id=$1 and id<>$2)", user_id, vehicle_id
                    )
                    if not other:
                        raise ApiError(409, "DEFAULT_VEHICLE_REQUIRED", "Add or select another vehicle before clearing the default")
                    replacement = await connection.fetchval(
                        "select id from public.driver_vehicles where user_id=$1 and id<>$2 order by created_at,id limit 1",
                        user_id, vehicle_id,
                    )
                    await connection.execute("update public.driver_vehicles set is_default=true where id=$1", replacement)
                if changes.get("is_default") is not None:
                    updates["is_default"] = bool(changes["is_default"])
                if updates:
                    assignments = ",".join(f"{key}=${index}" for index, key in enumerate(updates, 1))
                    values = list(updates.values()) + [vehicle_id, user_id]
                    row = await connection.fetchrow(
                        f"""update public.driver_vehicles set {assignments},updated_at=now()
                            where id=${len(values)-1} and user_id=${len(values)}
                            returning id,user_id,make,model,vehicle_type,battery_kwh,efficiency_km_per_kwh,
                                      current_soc,connector_compatibility,is_default,created_at,updated_at""", *values,
                    )
                else:
                    row = await connection.fetchrow(
                        """select id,user_id,make,model,vehicle_type,battery_kwh,efficiency_km_per_kwh,
                                  current_soc,connector_compatibility,is_default,created_at,updated_at
                           from public.driver_vehicles where id=$1 and user_id=$2""", vehicle_id, user_id,
                    )
                if row and row["is_default"]:
                    await connection.execute(
                        """update public.profiles set car_model=$2,battery_kwh=$3,
                                  default_efficiency_km_per_kwh=$4,current_soc=$5,updated_at=now() where id=$1""",
                        user_id, f"{row['make']} {row['model']}", row["battery_kwh"],
                        row["efficiency_km_per_kwh"], row["current_soc"],
                    )
                elif changes.get("is_default") is False:
                    replacement = await connection.fetchrow(
                        """select make,model,battery_kwh,efficiency_km_per_kwh,current_soc
                           from public.driver_vehicles where user_id=$1 and is_default limit 1""", user_id,
                    )
                    if replacement is not None:
                        await connection.execute(
                            """update public.profiles set car_model=$2,battery_kwh=$3,
                                      default_efficiency_km_per_kwh=$4,current_soc=$5,updated_at=now() where id=$1""",
                            user_id, f"{replacement['make']} {replacement['model']}", replacement["battery_kwh"],
                            replacement["efficiency_km_per_kwh"], replacement["current_soc"],
                        )
        return _record_value(row)

    async def select_default_driver_vehicle(self, user_id: UUID, vehicle_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.fetchrow("select id from public.profiles where id=$1 for update", user_id)
                selected = await connection.fetchrow(
                    """select id,user_id,make,model,vehicle_type,battery_kwh,efficiency_km_per_kwh,
                              current_soc,connector_compatibility,is_default,created_at,updated_at
                       from public.driver_vehicles where user_id=$1 and id=$2 for update""", user_id, vehicle_id,
                )
                if selected is None:
                    return None
                await connection.execute("update public.driver_vehicles set is_default=false where user_id=$1", user_id)
                row = await connection.fetchrow(
                    """update public.driver_vehicles set is_default=true,updated_at=now()
                       where id=$1 and user_id=$2
                       returning id,user_id,make,model,vehicle_type,battery_kwh,efficiency_km_per_kwh,
                                 current_soc,connector_compatibility,is_default,created_at,updated_at""",
                    vehicle_id, user_id,
                )
                await connection.execute(
                    """update public.profiles set car_model=$2,battery_kwh=$3,
                              default_efficiency_km_per_kwh=$4,current_soc=$5,updated_at=now() where id=$1""",
                    user_id, f"{selected['make']} {selected['model']}", selected["battery_kwh"],
                    selected["efficiency_km_per_kwh"], selected["current_soc"],
                )
        return _record_value(row)

    async def delete_driver_vehicle(self, user_id: UUID, vehicle_id: UUID) -> bool:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.fetchrow("select id from public.profiles where id=$1 for update", user_id)
                current = await connection.fetchrow(
                    "select id,is_default from public.driver_vehicles where user_id=$1 and id=$2 for update",
                    user_id, vehicle_id,
                )
                if current is None:
                    return False
                await connection.execute("delete from public.driver_vehicles where id=$1 and user_id=$2", vehicle_id, user_id)
                if current["is_default"]:
                    replacement = await connection.fetchrow(
                        """update public.driver_vehicles set is_default=true,updated_at=now()
                           where id=(select id from public.driver_vehicles where user_id=$1 order by created_at,id limit 1)
                           returning make,model,battery_kwh,efficiency_km_per_kwh,current_soc""", user_id,
                    )
                    if replacement is not None:
                        await connection.execute(
                            """update public.profiles set car_model=$2,battery_kwh=$3,
                                      default_efficiency_km_per_kwh=$4,current_soc=$5,updated_at=now() where id=$1""",
                            user_id, f"{replacement['make']} {replacement['model']}", replacement["battery_kwh"],
                            replacement["efficiency_km_per_kwh"], replacement["current_soc"],
                        )
        return True

    async def nearby_vendors(self, lat: float, lng: float, radius_km: float) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "select vendor, distance_km, services, available_slots from public.nearby_vendors($1, $2, $3)",
                lat,
                lng,
                radius_km,
            )
        result = []
        for row in rows:
            item = _record_value(row) or {}
            item["availability"] = item.pop("available_slots", [])
            result.append(item)
        return result

    async def save_driver_route(self, user_id: UUID, request: Any, route: dict[str, Any]) -> UUID:
        geojson = json.dumps({"type": "LineString", "coordinates": route["route_coordinates"]})
        distance_meters = int(round(float(route["distance_km"]) * 1000))
        async with self.pool.acquire() as connection:
            route_id = await connection.fetchval(
                """insert into public.routes (
                     user_id, origin, destination, corridor, distance_meters, distance_source,
                     battery_kwh, current_soc, efficiency_km_per_kwh, departure_at,
                     estimated_consumption_kwh, estimated_remaining_soc, route_geojson
                   ) values (
                     $1, $2, $3, 'NH-16', $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb
                   ) returning id""",
                user_id,
                route["origin"],
                route["destination"],
                distance_meters,
                route["distance_source"],
                request.battery_kwh,
                request.current_soc,
                request.efficiency_km_per_kwh,
                request.departure_at,
                route["estimated_consumption_kwh"],
                route["estimated_remaining_soc"],
                geojson,
            )
        return route_id

    async def _driver_trip(self, connection: asyncpg.Connection, user_id: UUID, trip_id: UUID) -> dict[str, Any] | None:
        row = await connection.fetchrow(
            """select t.id,t.driver_id,t.vehicle_id,t.route_id,t.origin,t.destination,
                      t.departure_at,t.estimated_arrival_at,t.vehicle_make,t.vehicle_model,
                      t.available_seats,t.notes,t.is_discoverable,t.status,t.started_at,
                      t.completed_at,t.cancelled_at,t.created_at,t.updated_at,
                      case when r.id is null then null else jsonb_build_object(
                        'id',r.id,'corridor',r.corridor,'distance_meters',r.distance_meters,
                        'distance_source',r.distance_source,'battery_kwh',r.battery_kwh,
                        'current_soc',r.current_soc,'efficiency_km_per_kwh',r.efficiency_km_per_kwh,
                        'estimated_consumption_kwh',r.estimated_consumption_kwh,
                        'estimated_remaining_soc',r.estimated_remaining_soc,
                        'route_geojson',r.route_geojson
                      ) end as route_plan
               from public.driver_trips t
               left join public.routes r on r.id=t.route_id
               where t.driver_id=$1 and t.id=$2""",
            user_id,
            trip_id,
        )
        return _record_value(row)

    async def driver_trip(self, user_id: UUID, trip_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            return await self._driver_trip(connection, user_id, trip_id)

    async def driver_trips(self, user_id: UUID, bucket: str = "upcoming") -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select t.id,t.driver_id,t.vehicle_id,t.route_id,t.origin,t.destination,
                          t.departure_at,t.estimated_arrival_at,t.vehicle_make,t.vehicle_model,
                          t.available_seats,t.notes,t.is_discoverable,t.status,t.started_at,
                          t.completed_at,t.cancelled_at,t.created_at,t.updated_at,
                          case when r.id is null then null else jsonb_build_object(
                            'id',r.id,'corridor',r.corridor,'distance_meters',r.distance_meters,
                            'distance_source',r.distance_source,'battery_kwh',r.battery_kwh,
                            'current_soc',r.current_soc,'efficiency_km_per_kwh',r.efficiency_km_per_kwh,
                            'estimated_consumption_kwh',r.estimated_consumption_kwh,
                            'estimated_remaining_soc',r.estimated_remaining_soc
                          ) end as route_plan
                   from public.driver_trips t
                   left join public.routes r on r.id=t.route_id
                   where t.driver_id=$1 and (
                     $2='all'
                     or ($2='upcoming' and t.status in ('scheduled','in_progress')
                         and (t.status='in_progress' or t.departure_at > now()))
                     or ($2='past' and (t.status in ('completed','cancelled')
                                       or (t.status='scheduled' and t.departure_at <= now())))
                   )
                   order by case when $2='past' then t.departure_at end desc,
                            case when $2<>'past' then t.departure_at end asc
                   limit 100""",
                user_id,
                bucket,
            )
        return [_record_value(row) or {} for row in rows]

    async def discover_driver_trips(
        self,
        viewer_id: UUID,
        origin: str | None,
        destination: str | None,
        departure_from: Any,
        departure_before: Any,
        limit: int,
    ) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select t.id,t.origin,t.destination,t.departure_at,t.estimated_arrival_at,
                          t.vehicle_make,t.vehicle_model,t.available_seats,t.status,
                          r.distance_meters,r.distance_source,r.estimated_consumption_kwh
                   from public.driver_trips t
                   left join public.routes r on r.id=t.route_id
                   where t.is_discoverable and t.status='scheduled'
                     and t.departure_at > now() and t.driver_id <> $1
                     and ($2::text is null or lower(t.origin) like lower($2) || '%')
                     and ($3::text is null or lower(t.destination) like lower($3) || '%')
                     and ($4::timestamptz is null or t.departure_at >= $4)
                     and ($5::timestamptz is null or t.departure_at < $5)
                   order by t.departure_at asc limit $6""",
                viewer_id,
                origin,
                destination,
                departure_from,
                departure_before,
                limit,
            )
        return [_record_value(row) or {} for row in rows]

    async def create_driver_trip(
        self,
        user_id: UUID,
        values: dict[str, Any],
        idempotency_key: str,
        request_fingerprint: str,
        route_plan: dict[str, Any] | None,
    ) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                vehicle = await connection.fetchrow(
                    """select id,make,model,battery_kwh,current_soc,efficiency_km_per_kwh
                       from public.driver_vehicles
                       where user_id=$1 and id=$2 for key share""",
                    user_id,
                    values["vehicle_id"],
                )
                if vehicle is None:
                    raise ApiError(404, "VEHICLE_NOT_FOUND", "Choose one of your saved vehicles")

                existing = await connection.fetchrow(
                    "select id,request_fingerprint from public.driver_trips where driver_id=$1 and idempotency_key=$2",
                    user_id,
                    idempotency_key,
                )
                if existing is not None:
                    if existing["request_fingerprint"] != request_fingerprint:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This request key was already used for different trip details")
                    trip = await self._driver_trip(connection, user_id, existing["id"])
                    return trip or {}

                if values["departure_at"] <= datetime.now(timezone.utc):
                    raise ApiError(422, "INVALID_TRIP_DATE", "A new trip must depart in the future")

                trip = await connection.fetchrow(
                    """insert into public.driver_trips
                         (driver_id,vehicle_id,origin,destination,departure_at,estimated_arrival_at,
                          vehicle_make,vehicle_model,available_seats,notes,is_discoverable,
                          idempotency_key,request_fingerprint)
                       values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                       on conflict (driver_id,idempotency_key) do nothing
                       returning id""",
                    user_id,
                    vehicle["id"],
                    values["origin"],
                    values["destination"],
                    values["departure_at"],
                    values.get("estimated_arrival_at"),
                    vehicle["make"],
                    vehicle["model"],
                    values["available_seats"],
                    values.get("notes"),
                    values["is_discoverable"],
                    idempotency_key,
                    request_fingerprint,
                )
                if trip is None:
                    existing = await connection.fetchrow(
                        "select id,request_fingerprint from public.driver_trips where driver_id=$1 and idempotency_key=$2",
                        user_id,
                        idempotency_key,
                    )
                    if existing is None or existing["request_fingerprint"] != request_fingerprint:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This request key was already used for different trip details")
                    result = await self._driver_trip(connection, user_id, existing["id"])
                    return result or {}

                trip_id = trip["id"]
                if route_plan is not None:
                    geojson = json.dumps({"type": "LineString", "coordinates": route_plan["route_coordinates"]})
                    route_id = await connection.fetchval(
                        """insert into public.routes (
                             user_id,origin,destination,corridor,distance_meters,distance_source,
                             battery_kwh,current_soc,efficiency_km_per_kwh,departure_at,
                             estimated_consumption_kwh,estimated_remaining_soc,route_geojson
                           ) values($1,$2,$3,'NH-16',$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
                           returning id""",
                        user_id,
                        route_plan["origin"],
                        route_plan["destination"],
                        int(round(float(route_plan["distance_km"]) * 1000)),
                        route_plan["distance_source"],
                        Decimal(str(vehicle["battery_kwh"])),
                        Decimal(str(values["current_soc"])),
                        Decimal(str(vehicle["efficiency_km_per_kwh"])),
                        values["departure_at"],
                        Decimal(str(route_plan["estimated_consumption_kwh"])),
                        Decimal(str(route_plan["estimated_remaining_soc"])),
                        geojson,
                    )
                    await connection.execute(
                        "update public.driver_trips set route_id=$2 where id=$1 and driver_id=$3",
                        trip_id,
                        route_id,
                        user_id,
                    )
                return await self._driver_trip(connection, user_id, trip_id) or {}

    async def update_driver_trip(
        self,
        user_id: UUID,
        trip_id: UUID,
        values: dict[str, Any],
        route_plan: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    """select id,status,departure_at from public.driver_trips
                       where id=$1 and driver_id=$2 for update""",
                    trip_id,
                    user_id,
                )
                if current is None:
                    return None
                if current["status"] != "scheduled" or current["departure_at"] <= datetime.now(timezone.utc):
                    raise ApiError(409, "TRIP_NOT_EDITABLE", "Only trips that are still scheduled can be edited")
                if values["departure_at"] <= datetime.now(timezone.utc):
                    raise ApiError(422, "INVALID_TRIP_DATE", "A trip departure must remain in the future")

                vehicle = await connection.fetchrow(
                    """select id,make,model,battery_kwh,efficiency_km_per_kwh
                       from public.driver_vehicles where id=$1 and user_id=$2 for key share""",
                    values["vehicle_id"],
                    user_id,
                )
                if vehicle is None:
                    raise ApiError(404, "VEHICLE_NOT_FOUND", "Choose one of your saved vehicles")

                route_id = None
                if route_plan is not None:
                    geojson = json.dumps({"type": "LineString", "coordinates": route_plan["route_coordinates"]})
                    route_id = await connection.fetchval(
                        """insert into public.routes (
                             user_id,origin,destination,corridor,distance_meters,distance_source,
                             battery_kwh,current_soc,efficiency_km_per_kwh,departure_at,
                             estimated_consumption_kwh,estimated_remaining_soc,route_geojson
                           ) values($1,$2,$3,'NH-16',$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
                           returning id""",
                        user_id,
                        route_plan["origin"],
                        route_plan["destination"],
                        int(round(float(route_plan["distance_km"]) * 1000)),
                        route_plan["distance_source"],
                        Decimal(str(vehicle["battery_kwh"])),
                        Decimal(str(values["current_soc"])),
                        Decimal(str(vehicle["efficiency_km_per_kwh"])),
                        values["departure_at"],
                        Decimal(str(route_plan["estimated_consumption_kwh"])),
                        Decimal(str(route_plan["estimated_remaining_soc"])),
                        geojson,
                    )

                await connection.execute(
                    """update public.driver_trips set vehicle_id=$3,route_id=$4,origin=$5,destination=$6,
                         departure_at=$7,estimated_arrival_at=$8,vehicle_make=$9,vehicle_model=$10,
                         available_seats=$11,notes=$12,is_discoverable=$13
                       where id=$1 and driver_id=$2""",
                    trip_id,
                    user_id,
                    vehicle["id"],
                    route_id,
                    values["origin"],
                    values["destination"],
                    values["departure_at"],
                    values.get("estimated_arrival_at"),
                    vehicle["make"],
                    vehicle["model"],
                    values["available_seats"],
                    values.get("notes"),
                    values["is_discoverable"],
                )
                return await self._driver_trip(connection, user_id, trip_id)

    async def transition_driver_trip(
        self,
        user_id: UUID,
        trip_id: UUID,
        target_status: str,
    ) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                current = await connection.fetchrow(
                    "select status from public.driver_trips where id=$1 and driver_id=$2 for update",
                    trip_id,
                    user_id,
                )
                if current is None:
                    return None
                if current["status"] == target_status:
                    return await self._driver_trip(connection, user_id, trip_id)
                allowed = {
                    ("scheduled", "in_progress"): "started_at",
                    ("in_progress", "completed"): "completed_at",
                    ("scheduled", "cancelled"): "cancelled_at",
                }
                timestamp_column = allowed.get((current["status"], target_status))
                if timestamp_column is None:
                    raise ApiError(409, "INVALID_TRIP_TRANSITION", "This trip cannot move to that status")
                await connection.execute(
                    f"update public.driver_trips set status=$3,{timestamp_column}=now() where id=$1 and driver_id=$2",
                    trip_id,
                    user_id,
                    target_status,
                )
                return await self._driver_trip(connection, user_id, trip_id)

    async def vendor(self, vendor_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select jsonb_build_object(
                         'id', v.id, 'name', v.name, 'type', v.type,
                         'lat', v.lat, 'lng', v.lng, 'address', v.address,
                         'phone', v.phone, 'description', v.description,
                         'image_url', v.image_url,
                         'is_active', v.is_active, 'is_verified', v.is_verified
                       ) as vendor,
                       coalesce((select jsonb_agg(jsonb_build_object(
                         'id', s.id, 'service_type', s.service_type,
                         'display_name', s.display_name, 'description', s.description,
                         'capacity', s.capacity, 'availability', s.availability,
                         'price_inr', s.price_inr, 'is_active', s.is_active
                       ) order by s.service_type)
                       from public.vendor_services s
                       where s.vendor_id = v.id and s.is_active), '[]'::jsonb) as services,
                       coalesce((select jsonb_agg(jsonb_build_object(
                         'id', cs.id, 'service_type', cs.service_type, 'slot_start_time', cs.slot_start_time,
                         'slot_end_time', cs.slot_end_time, 'capacity', cs.capacity,
                         'price_inr', cs.price_inr
                       ) order by cs.slot_start_time)
                       from public.charging_slots cs
                       where cs.vendor_id = v.id and cs.status = 'available'
                          and cs.slot_end_time > now()
                          and exists (select 1 from public.vendor_services active_service
                            where active_service.vendor_id=v.id and active_service.service_type=cs.service_type
                              and active_service.is_active)), '[]'::jsonb) as availability
                   from public.vendors v
                   where v.id = $1 and v.is_active and v.is_verified""",
                vendor_id,
            )
        return _record_value(row)

    async def vendor_slots(self, vendor_id: UUID) -> list[dict[str, Any]] | None:
        async with self.pool.acquire() as connection:
            vendor_exists = await connection.fetchval(
                "select exists(select 1 from public.vendors where id=$1 and is_active and is_verified)",
                vendor_id,
            )
            if not vendor_exists:
                return None
            rows = await connection.fetch(
                """select id, vendor_id, service_type, slot_start_time, slot_end_time,
                          capacity, price_inr, status
                   from public.charging_slots
                   where vendor_id=$1 and status='available' and slot_end_time > now()
                     and exists (select 1 from public.vendor_services s
                       where s.vendor_id=$1 and s.service_type=charging_slots.service_type and s.is_active)
                   order by slot_start_time""",
                vendor_id,
            )
        return [_record_value(row) or {} for row in rows]

    async def slot(self, slot_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select cs.id, cs.vendor_id, cs.service_type, cs.slot_start_time, cs.slot_end_time,
                          cs.capacity, cs.price_inr, cs.status
                   from public.charging_slots cs
                   join public.vendors v on v.id=cs.vendor_id
                   where cs.id=$1 and cs.status='available' and cs.slot_end_time > now()
                     and v.is_active and v.is_verified
                     and exists (select 1 from public.vendor_services s
                       where s.vendor_id=v.id and s.service_type=cs.service_type and s.is_active)""",
                slot_id,
            )
        return _record_value(row)

    async def vendor_id_for_owner(self, owner_id: UUID) -> UUID | None:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "select id from public.vendors where owner_id=$1 order by created_at limit 2",
                owner_id,
            )
        if len(rows) > 1:
            raise ApiError(409, "MULTIPLE_VENDOR_PROFILES", "This account owns more than one vendor profile")
        return rows[0]["id"] if rows else None

    async def vendor_profile_for_owner(self, owner_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select v.id, v.name, v.type, v.phone, v.address, v.lat, v.lng,
                          v.description, v.image_url, v.operating_hours,
                          v.is_active, v.is_verified,
                          coalesce((select o.status from public.vendor_onboarding o where o.vendor_id=v.id),
                                   case when v.is_verified then 'approved' else 'pending' end) as verification_status,
                          (select case when o.status='changes_requested' then o.decision_reason end
                             from public.vendor_onboarding o where o.vendor_id=v.id) as decision_reason,
                          coalesce((select jsonb_agg(jsonb_build_object(
                            'id', s.id, 'service_type', s.service_type,
                            'display_name', s.display_name, 'description', s.description,
                            'price_inr', s.price_inr, 'capacity', s.capacity,
                            'availability', s.availability, 'is_active', s.is_active
                          ) order by s.service_type)
                          from public.vendor_services s where s.vendor_id=v.id), '[]'::jsonb) as services
                   from public.vendors v where v.owner_id=$1 order by v.created_at limit 2""",
                owner_id,
            )
            if row is None:
                return None
            count = await connection.fetchval(
                "select count(*) from public.vendors where owner_id=$1", owner_id
            )
            if count > 1:
                raise ApiError(409, "MULTIPLE_VENDOR_PROFILES", "This account owns more than one vendor profile")
        return _record_value(row)

    async def create_vendor_profile(self, owner_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await connection.fetchrow(
                    "select id from public.profiles where id=$1 for update", owner_id
                )
                existing = await connection.fetchval(
                    "select exists(select 1 from public.vendors where owner_id=$1)", owner_id
                )
                if existing:
                    raise ApiError(409, "VENDOR_PROFILE_EXISTS", "This account already has a vendor profile")
                row = await connection.fetchrow(
                    """insert into public.vendors
                         (owner_id, name, type, phone, address, lat, lng, description, image_url, operating_hours)
                       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                       returning id, name, type, phone, address, lat, lng, description,
                                 image_url, operating_hours, is_active, is_verified""",
                    owner_id, values["name"], values["type"], values.get("phone"),
                    values["address"], values["lat"], values["lng"], values.get("description"),
                    values.get("image_url"), values.get("operating_hours"),
                )
        profile = _record_value(row) or {}
        profile["verification_status"] = "pending"
        profile["decision_reason"] = None
        return profile

    async def update_vendor_profile(self, owner_id: UUID, vendor_id: UUID, updates: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"name", "type", "phone", "address", "lat", "lng", "description", "image_url", "operating_hours"}
        selected = [(key, value) for key, value in updates.items() if key in allowed]
        if not selected:
            return await self.vendor_profile_for_owner(owner_id)
        assignments = ", ".join(f"{column}=${index}" for index, (column, _) in enumerate(selected, start=1))
        values = [value for _, value in selected]
        values.extend([vendor_id, owner_id])
        async with self.pool.acquire() as connection:
            updated_id = await connection.fetchval(
                f"""update public.vendors set {assignments}, updated_at=now()
                    where id=${len(values)-1} and owner_id=${len(values)}
                    returning id""",
                *values,
            )
            if updated_id is not None:
                await connection.execute(
                    """update public.vendor_onboarding
                       set status='under_review', current_stage='verification', decision_reason=null,
                           submitted_at=now(), reviewed_by=null, reviewed_at=null, updated_at=now()
                       where vendor_id=$1 and status='changes_requested'""",
                    vendor_id,
                )
        if updated_id is None:
            return None
        return await self.vendor_profile_for_owner(owner_id)

    async def vendor_dashboard(self, owner_id: UUID, vendor_id: UUID) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select
                     (select count(*) from public.bookings b join public.payments p on p.id=b.payment_id
                      where b.vendor_id=v.id and b.vendor_acknowledgement='pending'
                        and b.status='confirmed' and p.status='captured' and p.webhook_verified) as pending_requests,
                     (select count(*) from public.bookings b join public.charging_slots cs on cs.id=b.slot_id
                      where b.vendor_id=v.id and b.status in ('confirmed','completed')
                        and cs.slot_start_time >= date_trunc('day', now())
                        and cs.slot_start_time < date_trunc('day', now()) + interval '1 day') as todays_bookings,
                     (select coalesce(sum(greatest(cs.capacity - (
                       select count(*) from public.bookings b where b.slot_id=cs.id
                         and b.status in ('pending','confirmed')),0)),0) from public.charging_slots cs
                      where cs.vendor_id=v.id and cs.status='available'
                        and cs.slot_start_time >= date_trunc('day', now())
                        and cs.slot_start_time < date_trunc('day', now()) + interval '1 day') as available_capacity,
                     (select coalesce(sum(p.amount_inr),0) from public.payments p
                      join public.bookings b on b.payment_id=p.id
                      where b.vendor_id=v.id and p.status='captured'
                        and p.updated_at >= date_trunc('day', now())
                        and p.updated_at < date_trunc('day', now()) + interval '1 day') as todays_revenue
                   from public.vendors v where v.id=$1 and v.owner_id=$2""",
                vendor_id, owner_id,
            )
            if row is None:
                raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor profile was not found")
            schedule = await connection.fetch(
                """select b.id as booking_id, b.status, b.vendor_acknowledgement,
                          b.amount_paid as amount_inr, cs.slot_start_time, cs.slot_end_time,
                          cs.service_type, p.status as payment_status, p.webhook_verified, pr.name as customer_name
                   from public.bookings b
                   join public.charging_slots cs on cs.id=b.slot_id
                   join public.profiles pr on pr.id=b.user_id
                   left join public.payments p on p.id=b.payment_id
                   where b.vendor_id=$1 and cs.slot_start_time >= date_trunc('day', now())
                     and cs.slot_start_time < date_trunc('day', now()) + interval '1 day'
                   order by cs.slot_start_time limit 12""",
                vendor_id,
            )
            requests = await connection.fetch(
                """select b.id as booking_id, b.status, b.vendor_acknowledgement,
                          b.amount_paid as amount_inr, cs.slot_start_time, cs.slot_end_time,
                          cs.service_type, p.status as payment_status, p.webhook_verified, pr.name as customer_name
                   from public.bookings b
                   join public.charging_slots cs on cs.id=b.slot_id
                   join public.profiles pr on pr.id=b.user_id
                   left join public.payments p on p.id=b.payment_id
                   where b.vendor_id=$1 and b.status='confirmed'
                     and b.vendor_acknowledgement='pending' and p.status='captured' and p.webhook_verified
                   order by cs.slot_start_time limit 8""",
                vendor_id,
            )
            activity = await connection.fetch(
                """select e.id, e.event_type, e.created_at, e.metadata, b.id as booking_id
                   from public.booking_events e join public.bookings b on b.id=e.booking_id
                   where b.vendor_id=$1 order by e.created_at desc limit 8""",
                vendor_id,
            )
        return {"metrics": _record_value(row), "schedule": [_record_value(item) for item in schedule],
                "requests": [_record_value(item) for item in requests],
                "activity": [_record_value(item) for item in activity]}

    async def vendor_available_capacity_slots(self, owner_id: UUID, vendor_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select cs.id, greatest(cs.capacity - (
                          select count(*) from public.bookings b where b.slot_id=cs.id
                            and b.status in ('pending','confirmed')),0) as available_capacity
                   from public.charging_slots cs join public.vendors v on v.id=cs.vendor_id
                   where cs.vendor_id=$1 and v.owner_id=$2 and cs.status='available'
                     and cs.slot_start_time >= date_trunc('day',now())
                     and cs.slot_start_time < date_trunc('day',now()) + interval '1 day'""",
                vendor_id, owner_id,
            )
        return [_record_value(item) or {} for item in rows]

    async def vendor_bookings(self, owner_id: UUID, vendor_id: UUID, status: str | None = None) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select b.id as booking_id, b.status, b.vendor_acknowledgement,
                          b.amount_paid as amount_inr, b.created_at,
                          p.status as payment_status, p.amount_inr as charged_amount_inr,
                          p.webhook_verified, cs.id as slot_id, cs.slot_start_time,
                          cs.slot_end_time, cs.capacity, cs.service_type,
                          pr.name as customer_name, pr.phone as customer_phone,
                          pr.car_model as ev_model, pr.battery_kwh,
                          coalesce(vs.display_name, initcap(replace(cs.service_type,'_',' '))) as service_name
                   from public.bookings b
                   join public.vendors v on v.id=b.vendor_id
                   join public.charging_slots cs on cs.id=b.slot_id
                   join public.profiles pr on pr.id=b.user_id
                   left join public.payments p on p.id=b.payment_id
                   left join public.vendor_services vs on vs.vendor_id=b.vendor_id
                     and vs.service_type=cs.service_type
                   where b.vendor_id=$1 and v.owner_id=$2 and ($3::text is null or b.status=$3)
                   order by cs.slot_start_time desc limit 250""",
                vendor_id, owner_id, status,
            )
        return [_record_value(item) or {} for item in rows]

    async def vendor_booking(self, owner_id: UUID, vendor_id: UUID, booking_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select b.id as booking_id, b.status, b.vendor_acknowledgement,
                          b.amount_paid as amount_inr, b.created_at, b.updated_at,
                          p.status as payment_status, p.amount_inr as charged_amount_inr,
                          p.currency, p.webhook_verified, cs.id as slot_id,
                          cs.slot_start_time, cs.slot_end_time, cs.capacity, cs.service_type,
                          v.id as vendor_id, v.name as vendor_name,
                          pr.id as customer_id, pr.name as customer_name,
                          pr.phone as customer_phone, pr.car_model as ev_model,
                          pr.battery_kwh,
                          coalesce(vs.display_name, initcap(replace(cs.service_type,'_',' '))) as service_name,
                          coalesce((select jsonb_agg(jsonb_build_object(
                            'event_type', e.event_type, 'created_at', e.created_at, 'metadata', e.metadata
                          ) order by e.created_at)
                          from public.booking_events e where e.booking_id=b.id), '[]'::jsonb) as timeline
                   from public.bookings b
                   join public.vendors v on v.id=b.vendor_id
                   join public.charging_slots cs on cs.id=b.slot_id
                   join public.profiles pr on pr.id=b.user_id
                   left join public.payments p on p.id=b.payment_id
                   left join public.vendor_services vs on vs.vendor_id=b.vendor_id and vs.service_type=cs.service_type
                   where b.vendor_id=$1 and v.owner_id=$2 and b.id=$3""",
                vendor_id, owner_id, booking_id,
            )
        return _record_value(row)

    async def vendor_booking_action(self, owner_id: UUID, vendor_id: UUID, booking_id: UUID, action: str) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """select b.id, b.status, b.vendor_acknowledgement, b.slot_id,
                              p.status as payment_status, p.webhook_verified
                       from public.bookings b
                       join public.vendors v on v.id=b.vendor_id
                       join public.payments p on p.id=b.payment_id
                       where b.id=$1 and b.vendor_id=$2 and v.owner_id=$3
                       for update of b, p""",
                    booking_id, vendor_id, owner_id,
                )
                if row is None:
                    raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
                if row["status"] != "confirmed" or row["payment_status"] != "captured" or not row["webhook_verified"]:
                    raise ApiError(409, "BOOKING_NOT_PAID", "Vendor actions require a webhook-confirmed payment")
                if action == "accept":
                    if row["vendor_acknowledgement"] == "pending":
                        await connection.execute(
                            "update public.bookings set vendor_acknowledgement='accepted', updated_at=now() where id=$1",
                            booking_id,
                        )
                        await connection.execute(
                            "insert into public.booking_events (booking_id,event_type) values ($1,'vendor_accepted')",
                            booking_id,
                        )
                elif action == "complete":
                    if row["vendor_acknowledgement"] != "accepted":
                        raise ApiError(409, "BOOKING_NOT_ACCEPTED", "Accept this paid booking before completing it")
                    await connection.execute(
                        "update public.bookings set status='completed', updated_at=now() where id=$1",
                        booking_id,
                    )
                    await connection.execute(
                        "insert into public.booking_events (booking_id,event_type) values ($1,'vendor_completed')",
                        booking_id,
                    )
                else:
                    raise ApiError(422, "INVALID_VENDOR_ACTION", "Unsupported vendor booking action")
        booking = await self.vendor_booking(owner_id, vendor_id, booking_id)
        if booking is None:
            raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
        return booking

    async def vendor_slots_for_owner(self, owner_id: UUID, vendor_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select cs.id, cs.vendor_id, cs.slot_start_time, cs.slot_end_time,
                          cs.capacity, cs.price_inr, cs.status, cs.service_type,
                          (select count(*) from public.bookings b where b.slot_id=cs.id
                           and b.status in ('pending','confirmed')) as active_bookings,
                          (select count(*) from public.bookings b where b.slot_id=cs.id) as booking_history
                   from public.charging_slots cs join public.vendors v on v.id=cs.vendor_id
                   where cs.vendor_id=$1 and v.owner_id=$2 order by cs.slot_start_time desc limit 500""",
                vendor_id, owner_id,
            )
        return [_record_value(item) or {} for item in rows]

    async def create_vendor_slot(self, owner_id: UUID, vendor_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            service_exists = await connection.fetchval(
                "select exists(select 1 from public.vendor_services where vendor_id=$1 and service_type=$2 and is_active)",
                vendor_id, values["service_type"],
            )
            if not service_exists:
                raise ApiError(422, "SERVICE_REQUIRED", "Enable this service before adding an availability slot")
            row = await connection.fetchrow(
                """insert into public.charging_slots
                     (vendor_id, slot_start_time, slot_end_time, capacity, price_inr, service_type)
                   select $1,$2,$3,$4,$5,$6 where exists(
                     select 1 from public.vendors where id=$1 and owner_id=$7)
                   returning id, vendor_id, slot_start_time, slot_end_time, capacity, price_inr, status, service_type""",
                vendor_id, values["slot_start_time"], values["slot_end_time"],
                values["capacity"], values["price_inr"], values["service_type"], owner_id,
            )
        if row is None:
            raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor profile was not found")
        return _record_value(row) or {}

    async def update_vendor_slot(self, owner_id: UUID, vendor_id: UUID, slot_id: UUID, updates: dict[str, Any], slot_locked: bool = False) -> dict[str, Any]:
        allowed = {"slot_start_time", "slot_end_time", "capacity", "price_inr", "service_type", "status"}
        selected = [(key, value) for key, value in updates.items() if key in allowed]
        if not selected:
            raise ApiError(422, "EMPTY_PATCH", "Provide at least one slot field to update")
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                slot = await connection.fetchrow(
                    """select cs.* from public.charging_slots cs join public.vendors v on v.id=cs.vendor_id
                       where cs.id=$1 and cs.vendor_id=$2 and v.owner_id=$3 for update of cs""",
                    slot_id, vendor_id, owner_id,
                )
                if slot is None:
                    raise ApiError(404, "SLOT_NOT_FOUND", "Slot was not found")
                if slot_locked:
                    raise ApiError(409, "SLOT_TEMPORARILY_LOCKED", "A driver is holding this slot for booking")
                next_start = updates.get("slot_start_time", slot["slot_start_time"])
                next_end = updates.get("slot_end_time", slot["slot_end_time"])
                if next_end <= next_start:
                    raise ApiError(422, "INVALID_SLOT_TIME", "Slot end must be after slot start")
                active = await connection.fetchval(
                    "select count(*) from public.bookings where slot_id=$1 and status in ('pending','confirmed')",
                    slot_id,
                )
                if active and any(key in updates for key in ("slot_start_time", "slot_end_time", "price_inr", "service_type")):
                    raise ApiError(409, "SLOT_HAS_ACTIVE_BOOKINGS", "Time, price, and service cannot change while bookings are active")
                if "capacity" in updates and updates["capacity"] < slot["capacity"] and active >= updates["capacity"]:
                    raise ApiError(409, "CAPACITY_BELOW_BOOKINGS", "Capacity cannot be lower than active bookings")
                next_type = updates.get("service_type", slot["service_type"])
                next_status = updates.get("status", slot["status"])
                if next_status == "available":
                    service_enabled = await connection.fetchval(
                        "select exists(select 1 from public.vendor_services where vendor_id=$1 and service_type=$2 and is_active)",
                        vendor_id, next_type,
                    )
                    if not service_enabled:
                        raise ApiError(422, "SERVICE_REQUIRED", "Enable the slot's service before opening it")
                assignments = ", ".join(f"{key}=${index}" for index, (key, _) in enumerate(selected, start=1))
                values = [value for _, value in selected]
                values.extend([slot_id, vendor_id, owner_id])
                row = await connection.fetchrow(
                    f"""update public.charging_slots cs set {assignments}, updated_at=now()
                        from public.vendors v
                        where cs.id=${len(values)-2} and cs.vendor_id=${len(values)-1}
                          and v.id=cs.vendor_id and v.owner_id=${len(values)}
                        returning cs.id, cs.vendor_id, cs.slot_start_time, cs.slot_end_time,
                                  cs.capacity, cs.price_inr, cs.status, cs.service_type""",
                    *values,
                )
        return _record_value(row) or {}

    async def vendor_services(self, owner_id: UUID, vendor_id: UUID) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select s.id, s.vendor_id, s.service_type, s.display_name, s.description,
                          s.price_inr, s.capacity, s.availability, s.is_active
                   from public.vendor_services s join public.vendors v on v.id=s.vendor_id
                   where s.vendor_id=$1 and v.owner_id=$2 order by s.service_type""",
                vendor_id, owner_id,
            )
        return [_record_value(item) or {} for item in rows]

    async def create_vendor_service(self, owner_id: UUID, vendor_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    """insert into public.vendor_services
                         (vendor_id, service_type, display_name, description, price_inr, capacity, availability, is_active)
                       select $1,$2,$3,$4,$5,$6,$7,$8 where exists(
                         select 1 from public.vendors where id=$1 and owner_id=$9)
                       returning id, vendor_id, service_type, display_name, description,
                                 price_inr, capacity, availability, is_active""",
                    vendor_id, values["service_type"], values["display_name"], values.get("description"),
                    values["price_inr"], values.get("capacity"), json.dumps(values["availability"]),
                    values["is_active"], owner_id,
                )
        except asyncpg.UniqueViolationError as exc:
            raise ApiError(
                409,
                "SERVICE_TYPE_ALREADY_EXISTS",
                "A service of this type already exists. Edit the existing service instead.",
            ) from exc
        except asyncpg.CheckViolationError as exc:
            raise ApiError(
                422,
                "SERVICE_TYPE_UNAVAILABLE",
                "This service type is not supported by the current service catalogue.",
            ) from exc
        if row is None:
            raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor profile was not found")
        return _record_value(row) or {}

    async def update_vendor_service(self, owner_id: UUID, vendor_id: UUID, service_id: UUID, updates: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"service_type", "display_name", "description", "price_inr", "capacity", "availability", "is_active"}
        selected = [(key, value) for key, value in updates.items() if key in allowed]
        if not selected:
            raise ApiError(422, "EMPTY_PATCH", "Provide at least one service field to update")
        assignments = ", ".join(f"{key}=${index}" for index, (key, _) in enumerate(selected, start=1))
        # asyncpg's default JSON/JSONB codec accepts JSON text, not Python dicts.
        values = [
            json.dumps(value) if key == "availability" and value is not None else value
            for key, value in selected
        ]
        values.extend([service_id, vendor_id, owner_id])
        async with self.pool.acquire() as connection:
            if "service_type" in updates:
                used = await connection.fetchval(
                    """select exists(select 1 from public.charging_slots
                       where vendor_id=$1 and service_type=(select service_type from public.vendor_services where id=$2 and vendor_id=$1))""",
                    vendor_id, service_id,
                )
                if used:
                    raise ApiError(409, "SERVICE_IN_USE", "Service type cannot change while availability slots use it")
            row = await connection.fetchrow(
                f"""update public.vendor_services s set {assignments}, updated_at=now()
                    from public.vendors v where s.id=${len(values)-2} and s.vendor_id=${len(values)-1}
                    and v.id=s.vendor_id and v.owner_id=${len(values)}
                    returning s.id, s.vendor_id, s.service_type, s.display_name, s.description,
                              s.price_inr, s.capacity, s.availability, s.is_active""",
                *values,
            )
        return _record_value(row)

    async def vendor_revenue(self, owner_id: UUID, vendor_id: UUID) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select
                     coalesce(sum(p.amount_inr) filter (where p.status='captured' and p.webhook_verified and p.updated_at >= date_trunc('day',now())),0) as today_gross,
                     coalesce(sum(p.amount_inr) filter (where p.status='captured' and p.webhook_verified and p.updated_at >= date_trunc('week',now())),0) as week_gross,
                     coalesce(sum(p.amount_inr) filter (where p.status='captured' and p.webhook_verified and p.updated_at >= date_trunc('month',now())),0) as month_gross,
                     coalesce(sum(c.captured_amount_inr),0) as all_time_gross,
                     coalesce(sum(r.completed_refunds),0) as completed_refunds,
                     coalesce(sum(round(greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                       * c.rate_bps::numeric/10000::numeric,2)),0) as platform_fee,
                     coalesce(sum(greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                       - round(greatest(c.captured_amount_inr-coalesce(r.completed_refunds,0),0)
                         * c.rate_bps::numeric/10000::numeric,2)),0) as estimated_payout,
                     (select rate_bps from public.platform_commission_settings where id=1) as commission_rate_bps,
                     count(b.id) as total_bookings,
                     count(*) filter (where b.status='completed') as completed_bookings,
                     count(*) filter (where b.status='cancelled') as cancelled_bookings,
                     count(*) filter (where p.status='captured' and p.webhook_verified) as captured_payments,
                     count(*) filter (where p.status='refunded') as refunded_payments
                   from public.vendors v
                   left join public.bookings b on b.vendor_id=v.id
                   left join public.payments p on p.id=b.payment_id
                   left join public.payment_commission_ledger c on c.payment_id=p.id
                   left join lateral (select coalesce(sum(rf.amount_inr),0) as completed_refunds
                     from public.refunds rf where rf.payment_id=p.id and rf.status='completed') r on true
                   where v.id=$1 and v.owner_id=$2 group by v.id""",
                vendor_id, owner_id,
            )
        if row is None:
            raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor profile was not found")
        return _record_value(row) or {}

    async def recommended_pitstops(self, route_geojson: str) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """with route as (
                     select extensions.st_setsrid(extensions.st_geomfromgeojson($1), 4326) as geom
                   )
                   select jsonb_build_object(
                     'id', v.id, 'name', v.name, 'type', v.type,
                     'lat', v.lat, 'lng', v.lng, 'address', v.address,
                     'image_url', v.image_url
                   ) as vendor,
                   extensions.st_distance(v.location, route.geom::extensions.geography) / 1000.0 as distance_km,
                   coalesce((select jsonb_agg(jsonb_build_object(
                     'service_type', s.service_type, 'price_inr', s.price_inr
                   ) order by s.service_type)
                   from public.vendor_services s where s.vendor_id=v.id and s.is_active), '[]'::jsonb) as services,
                   extensions.st_linelocatepoint(route.geom, v.location::extensions.geometry) as route_progress
                   from public.vendors v cross join route
                   where v.is_active and v.is_verified
                     and extensions.st_dwithin(v.location, route.geom::extensions.geography, 15000)
                   order by route_progress, distance_km limit 20""",
                route_geojson,
            )
        return [_record_value(row) or {} for row in rows]

    async def create_pending_booking(
        self,
        user_id: UUID,
        slot_id: UUID,
        booking_id: UUID,
        razorpay_order_id: str,
        expected_amount: Decimal,
    ) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                slot = await connection.fetchrow(
                    """select cs.id, cs.vendor_id, cs.capacity, cs.price_inr,
                              cs.slot_start_time, cs.slot_end_time, cs.status,
                              cs.slot_end_time > now() as is_future,
                              v.is_active, v.is_verified
                       from public.charging_slots cs
                       join public.vendors v on v.id=cs.vendor_id
                       where cs.id=$1 for update of cs""",
                    slot_id,
                )
                if slot is None or not slot["is_active"] or not slot["is_verified"]:
                    raise ApiError(404, "SLOT_NOT_FOUND", "Available slot was not found")
                if slot["status"] != "available" or not slot["is_future"]:
                    raise ApiError(409, "SLOT_UNAVAILABLE", "Slot is no longer available")
                if Decimal(slot["price_inr"]) != expected_amount:
                    raise ApiError(409, "PRICE_CHANGED", "Slot price changed; please retry booking")
                active_count = await connection.fetchval(
                    "select count(*) from public.bookings where slot_id=$1 and status in ('pending','confirmed')",
                    slot_id,
                )
                if active_count >= slot["capacity"]:
                    await connection.execute(
                        "update public.charging_slots set status='booked' where id=$1 and status='available'",
                        slot_id,
                    )
                    raise ApiError(409, "SLOT_UNAVAILABLE", "Slot capacity has been reached")

                await connection.execute(
                    """insert into public.bookings
                         (id, user_id, vendor_id, slot_id, amount_paid, status)
                       values ($1, $2, $3, $4, 0, 'pending')""",
                    booking_id,
                    user_id,
                    slot["vendor_id"],
                    slot_id,
                )
                payment_id = await connection.fetchval(
                    """insert into public.payments
                         (booking_id, razorpay_order_id, amount_inr, currency, status)
                       values ($1, $2, $3, 'INR', 'pending') returning id""",
                    booking_id,
                    razorpay_order_id,
                    slot["price_inr"],
                )
                await connection.execute(
                    "update public.bookings set payment_id=$2 where id=$1",
                    booking_id,
                    payment_id,
                )
                await connection.execute(
                    "insert into public.booking_events (booking_id, event_type) values ($1, 'created'), ($1, 'payment_started')",
                    booking_id,
                )
                occupied = await connection.fetchval(
                    "select count(*) from public.bookings where slot_id=$1 and status in ('pending','confirmed')",
                    slot_id,
                )
                if occupied >= slot["capacity"]:
                    await connection.execute(
                        "update public.charging_slots set status='booked' where id=$1 and status='available'",
                        slot_id,
                    )
                row = await connection.fetchrow(
                    """select b.id, b.user_id, b.vendor_id, b.slot_id, b.payment_id,
                              b.amount_paid, b.status, b.created_at, b.updated_at,
                              p.razorpay_order_id, p.amount_inr, p.currency, p.status as payment_status,
                              v.name as vendor_name, v.address as vendor_address,
                              cs.slot_start_time, cs.slot_end_time
                       from public.bookings b
                       join public.payments p on p.id=b.payment_id
                       join public.vendors v on v.id=b.vendor_id
                       join public.charging_slots cs on cs.id=b.slot_id
                       where b.id=$1""",
                    booking_id,
                )
        return _record_value(row) or {}

    async def bookings(self, user_id: UUID, limit: int, offset: int) -> list[dict[str, Any]]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """select b.id, b.user_id, b.vendor_id, b.slot_id, b.payment_id,
                          b.amount_paid, b.status, b.created_at, b.updated_at,
                          p.razorpay_order_id, p.amount_inr, p.currency, p.status as payment_status,
                          v.name as vendor_name, v.address as vendor_address,
                          cs.slot_start_time, cs.slot_end_time
                   from public.bookings b
                   left join public.payments p on p.id=b.payment_id
                   join public.vendors v on v.id=b.vendor_id
                   join public.charging_slots cs on cs.id=b.slot_id
                   where b.user_id=$1 order by b.created_at desc limit $2 offset $3""",
                user_id,
                limit,
                offset,
            )
        return [_record_value(row) or {} for row in rows]

    async def booking(self, user_id: UUID, booking_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select b.id, b.user_id, b.vendor_id, b.slot_id, b.payment_id,
                          b.amount_paid, b.status, b.created_at, b.updated_at,
                          p.razorpay_order_id, p.amount_inr, p.currency, p.status as payment_status,
                          v.name as vendor_name, v.address as vendor_address,
                          cs.slot_start_time, cs.slot_end_time
                   from public.bookings b
                   left join public.payments p on p.id=b.payment_id
                   join public.vendors v on v.id=b.vendor_id
                   join public.charging_slots cs on cs.id=b.slot_id
                   where b.id=$1 and b.user_id=$2""",
                booking_id,
                user_id,
            )
            if row is None:
                exists = await connection.fetchval(
                    "select exists(select 1 from public.bookings where id=$1)", booking_id
                )
                if exists:
                    raise ApiError(403, "FORBIDDEN", "You cannot access this booking")
        return _record_value(row)

    async def cancel_booking(self, user_id: UUID, booking_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    "select id, slot_id, status from public.bookings where id=$1 and user_id=$2 for update",
                    booking_id,
                    user_id,
                )
                if row is None:
                    exists = await connection.fetchval(
                        "select exists(select 1 from public.bookings where id=$1)", booking_id
                    )
                    if exists:
                        raise ApiError(403, "FORBIDDEN", "You cannot cancel this booking")
                    return None
                if row["status"] != "pending":
                    raise ApiError(409, "BOOKING_NOT_CANCELLABLE", "Only pending bookings can be cancelled")
                await connection.execute(
                    "update public.bookings set status='cancelled' where id=$1", booking_id
                )
                await connection.execute(
                    "update public.payments set status='failed' where booking_id=$1 and status='pending'",
                    booking_id,
                )
                await connection.execute(
                    "insert into public.booking_events (booking_id, event_type) values ($1, 'cancelled')",
                    booking_id,
                )
                await connection.execute(
                    """update public.charging_slots cs set status='available'
                       where cs.id=$1 and cs.status='booked' and (
                         select count(*) from public.bookings b
                         where b.slot_id=cs.id and b.status in ('pending','confirmed')
                       ) < cs.capacity""",
                    row["slot_id"],
                )
                updated = await connection.fetchrow(
                    """select b.id, b.user_id, b.vendor_id, b.slot_id, b.payment_id,
                              b.amount_paid, b.status, b.created_at, b.updated_at,
                              p.razorpay_order_id, p.amount_inr, p.currency, p.status as payment_status
                       from public.bookings b left join public.payments p on p.id=b.payment_id
                       where b.id=$1""",
                    booking_id,
                )
        return _record_value(updated)

    async def process_payment_webhook(
        self, order_id: str, payment_id: str, amount_paise: int, currency: str, captured: bool
    ) -> bool:
        try:
            async with self.pool.acquire() as connection:
                async with connection.transaction():
                    payment = await connection.fetchrow(
                        """select id as payment_id, booking_id
                           from public.payments where razorpay_order_id=$1""",
                        order_id,
                    )
                    if payment is None:
                        return False

                    # Lock in the same booking-then-payment order used by cancellation.
                    # Requiring the payment pointer here protects against cross-booking
                    # association errors even if legacy data violates the schema FK.
                    booking = await connection.fetchrow(
                        """select id, payment_id, status as booking_status, slot_id
                           from public.bookings where id=$1 and payment_id=$2 for update""",
                        payment["booking_id"], payment["payment_id"],
                    )
                    if booking is None:
                        return False
                    row = await connection.fetchrow(
                        """select id as payment_id, booking_id, razorpay_order_id, amount_inr,
                                  currency, status as payment_status, razorpay_payment_id
                           from public.payments where id=$1 for update""",
                        payment["payment_id"],
                    )
                    if (row is None or row["booking_id"] != booking["id"]
                            or row["razorpay_order_id"] != order_id):
                        return False

                    # Verify every signed provider identifier and financial field before
                    # treating an event as a duplicate or allowing any state transition.
                    stored_payment_id = row["razorpay_payment_id"]
                    if stored_payment_id is not None and stored_payment_id != payment_id:
                        raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
                    if row["currency"].strip().upper() != currency.strip().upper():
                        raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
                    if int(Decimal(row["amount_inr"]) * 100) != amount_paise:
                        raise ApiError(400, "PAYMENT_AMOUNT_MISMATCH", "Webhook payment could not be verified")
                    duplicate_provider_payment = await connection.fetchrow(
                        """select id from public.payments
                           where razorpay_payment_id=$1 and id<>$2""",
                        payment_id, row["payment_id"],
                    )
                    if duplicate_provider_payment is not None:
                        raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")

                    current_status = row["payment_status"]
                    if current_status in ("captured", "refunded"):
                        # Captured/refunded are terminal against duplicate or older events.
                        if stored_payment_id is None:
                            raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
                        return True
                    if current_status == "failed" and not captured:
                        # Same-ID failure replay: acknowledge without another event/write.
                        if stored_payment_id is None:
                            raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
                        return True
                    if current_status not in ("pending", "authorized", "failed"):
                        raise ApiError(409, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")

                    await connection.execute(
                        """update public.payments set status=$2, webhook_verified=true,
                                  razorpay_payment_id=$3 where id=$1""",
                        row["payment_id"], "captured" if captured else "failed", payment_id,
                    )
                    event = "payment_success" if captured else "payment_failed"
                    await connection.execute(
                        "insert into public.booking_events (booking_id, event_type) values ($1, $2)",
                        row["booking_id"], event,
                    )
                    if captured and booking["booking_status"] == "pending":
                        await connection.execute(
                            "update public.bookings set status='confirmed', amount_paid=$2 where id=$1",
                            row["booking_id"], row["amount_inr"],
                        )
                        await connection.execute(
                            "insert into public.booking_events (booking_id, event_type) values ($1, 'confirmed')",
                            row["booking_id"],
                        )
                    elif not captured and booking["booking_status"] == "pending":
                        await connection.execute(
                            "update public.bookings set status='expired' where id=$1",
                            row["booking_id"],
                        )
                        await connection.execute(
                            "insert into public.booking_events (booking_id, event_type) values ($1, 'expired')",
                            row["booking_id"],
                        )
                        await connection.execute(
                            """update public.charging_slots cs set status='available'
                               where cs.id=$1 and cs.status='booked' and (
                                 select count(*) from public.bookings b
                                 where b.slot_id=cs.id and b.status in ('pending','confirmed')
                               ) < cs.capacity""",
                            booking["slot_id"],
                        )
        except asyncpg.UniqueViolationError as exc:
            # The unique provider-payment constraint is the final guard for a race
            # across two different locked payment rows.
            raise ApiError(409, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified") from exc
        return True

    async def process_refund_webhook(
        self, refund_id: str, payment_id: str, amount_paise: int, currency: str, provider_status: str,
        local_refund_id: str | None = None,
    ) -> bool:
        status_map = {"processed": "completed", "failed": "failed", "pending": "processing"}
        local_status = status_map.get(provider_status)
        if local_status is None:
            return False
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """select r.id,r.requested_by,r.payment_id,r.amount_inr,r.status,r.dispute_id,
                              r.razorpay_refund_id,p.currency,p.status as payment_status
                       from public.refunds r join public.payments p on p.id=r.payment_id
                       where (r.razorpay_refund_id=$1 or ($3::text is not null and r.id::text=$3))
                         and p.razorpay_payment_id=$2
                       for update of r""",
                    refund_id, payment_id, local_refund_id,
                )
                if row is None:
                    return False
                if row["razorpay_refund_id"] is not None and row["razorpay_refund_id"] != refund_id:
                    raise ApiError(400, "REFUND_WEBHOOK_REJECTED", "Webhook refund could not be verified")
                if row["currency"].strip().upper() != currency.strip().upper():
                    raise ApiError(400, "REFUND_WEBHOOK_REJECTED", "Webhook refund could not be verified")
                if int(Decimal(row["amount_inr"]) * 100) != amount_paise:
                    raise ApiError(400, "REFUND_AMOUNT_MISMATCH", "Refund webhook amount does not match the recorded refund")
                if row["status"] not in ("completed", "failed") and row["status"] != local_status:
                    await connection.execute(
                        "update public.refunds set razorpay_refund_id=coalesce(razorpay_refund_id,$2),status=$3,provider_status=$4,provider_error=null,updated_at=now() where id=$1",
                        row["id"], refund_id, local_status, provider_status,
                    )
                    await connection.execute(
                        """insert into public.admin_audit_logs(admin_user_id,role_name,action,entity_type,entity_id,
                             reason,before_state,after_state,request_metadata)
                           values($1,'PAYMENT_PROVIDER','refund.webhook_state','refund',$2,'Verified Razorpay webhook',
                             jsonb_build_object('status',$3),jsonb_build_object('status',$4,'provider_status',$5),
                             '{"source":"razorpay_webhook"}'::jsonb)""",
                        row["requested_by"], str(row["id"]), row["status"], local_status, provider_status,
                    )
                    if row["dispute_id"] is not None and local_status in ("completed", "failed"):
                        await connection.execute(
                            """insert into public.dispute_events(dispute_id,actor_type,event_type,message,metadata)
                               values($1,'system',$2,$3,$4::jsonb)""",
                            row["dispute_id"],
                            "refund_completed" if local_status == "completed" else "refund_failed",
                            f"Refund provider state: {provider_status}",
                            json.dumps({"role": "PAYMENT_PROVIDER", "refund_id": str(row["id"]),
                                        "provider_refund_id": refund_id, "before": {"status": row["status"]},
                                        "after": {"status": local_status}, "request": {"source": "razorpay_webhook"}}),
                        )
                if local_status == "completed" and row["payment_status"] != "refunded":
                    refunded = await connection.fetchval(
                        "select coalesce(sum(amount_inr),0) from public.refunds where payment_id=$1 and status='completed'",
                        row["payment_id"],
                    )
                    captured = await connection.fetchval(
                        "select amount_inr from public.payments where id=$1", row["payment_id"]
                    )
                    if Decimal(refunded) >= Decimal(captured):
                        await connection.execute(
                            "update public.payments set status='refunded',updated_at=now() where id=$1", row["payment_id"]
                        )
        return True

    async def create_customer_dispute(
        self, customer_id: UUID, booking_id: UUID, reason: str, description: str, idempotency_key: str,
        request_metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                replay = await connection.fetchrow(
                    """select d.id,d.booking_id,d.status,d.reason,d.description,d.amount_inr,d.created_at,d.updated_at
                       from public.dispute_events e join public.disputes d on d.id=e.dispute_id
                       where e.idempotency_key=$1 and e.actor_id=$2 and e.event_type='created'""",
                    idempotency_key, customer_id,
                )
                if replay is not None:
                    if (replay["booking_id"] != booking_id or replay["reason"] != reason
                            or replay["description"] != description):
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for a different dispute")
                    return _record_value(replay) or {}, False
                booking = await connection.fetchrow(
                    """select b.id,b.user_id,b.vendor_id,b.status,p.id as payment_id,p.amount_inr,
                              p.status as payment_status,p.webhook_verified
                       from public.bookings b left join public.payments p on p.id=b.payment_id
                       where b.id=$1 for update of b""", booking_id,
                )
                if booking is None:
                    raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
                if booking["user_id"] != customer_id:
                    raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
                if booking["status"] not in ("confirmed", "completed", "cancelled"):
                    raise ApiError(409, "BOOKING_NOT_ELIGIBLE_FOR_DISPUTE", "Only paid bookings can be disputed")
                if (booking["payment_id"] is None or booking["payment_status"] not in ("captured", "refunded")
                        or not booking["webhook_verified"]):
                    raise ApiError(409, "PAYMENT_NOT_VERIFIED", "A captured, verified payment is required for a dispute")
                active = await connection.fetchval(
                    """select exists(select 1 from public.disputes where booking_id=$1
                       and status in ('open','investigating','awaiting_customer','awaiting_vendor'))""", booking_id,
                )
                if active:
                    raise ApiError(409, "ACTIVE_DISPUTE_EXISTS", "This booking already has an active dispute")
                row = await connection.fetchrow(
                    """insert into public.disputes(booking_id,customer_id,vendor_id,amount_inr,reason,description,
                              status,created_by)
                       values($1,$2,$3,$4,$5,$6,'open',$2) returning id,booking_id,status,reason,description,
                              amount_inr,created_at,updated_at""",
                    booking_id, customer_id, booking["vendor_id"], booking["amount_inr"], reason, description,
                )
                await connection.execute(
                    """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,
                              message,metadata,idempotency_key)
                       values($1,$2,$2,'customer','created',$3,$4::jsonb,$5)""",
                    row["id"], customer_id, description,
                    json.dumps({"role": "CUSTOMER", "after": {"status": "open"}, "request": request_metadata or {}}),
                    idempotency_key,
                )
        return _record_value(row) or {}, True

    async def customer_disputes(self, customer_id: UUID, limit: int, offset: int) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            total = await connection.fetchval("select count(*) from public.disputes where customer_id=$1", customer_id)
            rows = await connection.fetch(
                """select id,booking_id,vendor_id,amount_inr,reason,description,status,created_at,updated_at,resolved_at
                   from public.disputes where customer_id=$1 order by created_at desc limit $2 offset $3""",
                customer_id, limit, offset,
            )
        return {"items": [_record_value(row) or {} for row in rows], "total": total, "limit": limit, "offset": offset}

    async def customer_dispute(self, customer_id: UUID, dispute_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select d.id,d.booking_id,d.customer_id,d.vendor_id,d.amount_inr,d.reason,d.description,d.status,
                          d.created_at,d.updated_at,d.resolved_at,
                          coalesce((select jsonb_agg(jsonb_build_object('id',e.id,'actor_type',e.actor_type,
                            'event_type',e.event_type,'message',e.message,'metadata',e.metadata,'created_at',e.created_at)
                            order by e.created_at) from public.dispute_events e where e.dispute_id=d.id),'[]'::jsonb) as timeline
                   from public.disputes d where d.id=$1 and d.customer_id=$2""", dispute_id, customer_id,
            )
        return _record_value(row)

    async def vendor_disputes(self, vendor_id: UUID, limit: int, offset: int) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            total = await connection.fetchval("select count(*) from public.disputes where vendor_id=$1", vendor_id)
            rows = await connection.fetch(
                """select id,booking_id,customer_id,amount_inr,reason,description,status,created_at,updated_at
                   from public.disputes where vendor_id=$1 order by created_at desc limit $2 offset $3""",
                vendor_id, limit, offset,
            )
        return {"items": [_record_value(row) or {} for row in rows], "total": total, "limit": limit, "offset": offset}

    async def vendor_dispute(self, vendor_id: UUID, dispute_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """select d.id,d.booking_id,d.customer_id,d.vendor_id,d.amount_inr,d.reason,d.description,d.status,
                          d.created_at,d.updated_at,
                          coalesce((select jsonb_agg(jsonb_build_object('id',e.id,'actor_type',e.actor_type,
                            'event_type',e.event_type,'message',e.message,'metadata',e.metadata,'created_at',e.created_at)
                            order by e.created_at) from public.dispute_events e where e.dispute_id=d.id),'[]'::jsonb) as timeline
                   from public.disputes d where d.id=$1 and d.vendor_id=$2""", dispute_id, vendor_id,
            )
        return _record_value(row)

    async def add_customer_dispute_message(self, customer_id: UUID, dispute_id: UUID, message: str,
                                           idempotency_key: str, request_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._add_dispute_message(customer_id, "customer", dispute_id, message, idempotency_key, request_metadata=request_metadata)

    async def add_vendor_dispute_message(self, vendor_id: UUID, actor_id: UUID, dispute_id: UUID,
                                         message: str, idempotency_key: str,
                                         request_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self.pool.acquire() as connection:
            owner = await connection.fetchval("select id from public.vendors where id=$1 and owner_id=$2", vendor_id, actor_id)
        if owner is None:
            raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
        return await self._add_dispute_message(actor_id, "vendor", dispute_id, message, idempotency_key, vendor_id, request_metadata)

    async def _add_dispute_message(self, actor_id: UUID, actor_type: str, dispute_id: UUID, message: str,
                                   idempotency_key: str, vendor_id: UUID | None = None,
                                   request_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        scope_column = "customer_id" if actor_type == "customer" else "vendor_id"
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                replay = await connection.fetchrow(
                    "select dispute_id,message,event_type from public.dispute_events where idempotency_key=$1 and actor_id=$2",
                    idempotency_key, actor_id,
                )
                if replay is not None:
                    event_type = "customer_message" if actor_type == "customer" else "vendor_message"
                    if replay["dispute_id"] != dispute_id or replay["message"] != message or replay["event_type"] != event_type:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for another dispute event")
                    result = await connection.fetchrow("select id,status from public.disputes where id=$1", dispute_id)
                    return _record_value(result) or {}
                scope_id = actor_id if actor_type == "customer" else vendor_id
                row = await connection.fetchrow(
                    f"select id,status from public.disputes where id=$1 and {scope_column}=$2 for update",
                    dispute_id, scope_id,
                )
                if row is None:
                    raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
                if row["status"] in ("resolved", "closed"):
                    raise ApiError(409, "DISPUTE_CLOSED", "This dispute no longer accepts messages")
                event_type = "customer_message" if actor_type == "customer" else "vendor_message"
                await connection.execute(
                    """insert into public.dispute_events(dispute_id,actor_user_id,actor_id,actor_type,event_type,
                              message,metadata,idempotency_key) values($1,$2,$2,$3,$4,$5,$6::jsonb,$7)""",
                    dispute_id, actor_id, actor_type, event_type, message,
                    json.dumps({"role": "CUSTOMER" if actor_type == "customer" else "VENDOR_OWNER",
                                "request": request_metadata or {}}), idempotency_key,
                )
                await connection.execute("update public.disputes set updated_at=now() where id=$1", dispute_id)
        result = await (self.customer_dispute(actor_id, dispute_id) if actor_type == "customer"
                        else self.vendor_dispute(vendor_id, dispute_id))
        return result or {}

    async def recommended_route_vendors(self, geojson: str) -> list[dict[str, Any]]:
        return await self.recommended_pitstops(geojson)
