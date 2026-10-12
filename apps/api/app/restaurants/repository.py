"""Server-authoritative menu pricing, order snapshots, and webhook state."""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from app.core.errors import ApiError


def _row(value):
    if value is None:
        return None
    result = dict(value)
    for key in ("options", "selected_options", "items"):
        if isinstance(result.get(key), str):
            result[key] = json.loads(result[key])
    return result


class RestaurantRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def menu(self, vendor_id: UUID) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            vendor = await conn.fetchrow("""select id,name,type,address,phone,image_url from public.vendors
                where id=$1 and type='restaurant' and is_active and is_verified""", vendor_id)
            if vendor is None:
                return None
            categories = await conn.fetch("""select c.id,c.name,c.sort_order,
                coalesce(jsonb_agg(jsonb_build_object('id',i.id,'name',i.name,'description',i.description,
                  'price_inr',i.price_inr,'is_available',i.is_available,'options',i.options)
                  order by i.name) filter (where i.id is not null and i.is_available), '[]'::jsonb) as items
                from public.restaurant_menu_categories c left join public.restaurant_menu_items i
                  on i.category_id=c.id and i.vendor_id=c.vendor_id
                where c.vendor_id=$1 and c.is_active group by c.id order by c.sort_order,c.name""", vendor_id)
        return {"vendor": _row(vendor), "categories": [_row(x) for x in categories]}

    async def vendor_menu(self, owner_id: UUID, vendor_id: UUID) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            await self._owned_restaurant(conn, owner_id, vendor_id)
            categories = await conn.fetch("""select c.id,c.name,c.sort_order,c.is_active,
              coalesce(jsonb_agg(jsonb_build_object('id',i.id,'name',i.name,'description',i.description,
              'price_inr',i.price_inr,'is_available',i.is_available,'options',i.options)
              order by i.name) filter(where i.id is not null),'[]'::jsonb) items
              from public.restaurant_menu_categories c left join public.restaurant_menu_items i
                on i.category_id=c.id and i.vendor_id=c.vendor_id
              where c.vendor_id=$1 group by c.id order by c.sort_order,c.name""", vendor_id)
        return {"categories": [_row(x) for x in categories]}

    async def _owned_restaurant(self, conn, owner_id, vendor_id):
        ok = await conn.fetchval("select exists(select 1 from public.vendors where id=$1 and owner_id=$2 and type='restaurant')", vendor_id, owner_id)
        if not ok:
            raise ApiError(404, "RESTAURANT_NOT_FOUND", "Authorized restaurant was not found")

    async def create_category(self, owner_id, vendor_id, name, sort_order):
        async with self.pool.acquire() as conn:
            await self._owned_restaurant(conn, owner_id, vendor_id)
            row = await conn.fetchrow("""insert into public.restaurant_menu_categories(vendor_id,name,sort_order)
              values($1,$2,$3) returning id,name,sort_order,is_active""", vendor_id, name.strip(), sort_order)
        return _row(row)

    async def upsert_item(self, owner_id, vendor_id, values, item_id=None):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._owned_restaurant(conn, owner_id, vendor_id)
                category_ok = await conn.fetchval("select exists(select 1 from public.restaurant_menu_categories where id=$1 and vendor_id=$2 and is_active)", values["category_id"], vendor_id)
                if not category_ok:
                    raise ApiError(422, "MENU_CATEGORY_INVALID", "Choose an active category belonging to this restaurant")
                if item_id is None:
                    row = await conn.fetchrow("""insert into public.restaurant_menu_items
                      (vendor_id,category_id,name,description,price_inr,is_available,options)
                      values($1,$2,$3,$4,$5,$6,$7::jsonb) returning *""", vendor_id, values["category_id"], values["name"].strip(), values.get("description"), values["price_inr"], values["is_available"], json.dumps(values.get("options", []), default=str))
                else:
                    row = await conn.fetchrow("""update public.restaurant_menu_items set category_id=$3,name=$4,
                      description=$5,price_inr=$6,is_available=$7,options=$8::jsonb,updated_at=now()
                      where id=$1 and vendor_id=$2 returning *""", item_id, vendor_id, values["category_id"], values["name"].strip(), values.get("description"), values["price_inr"], values["is_available"], json.dumps(values.get("options", []), default=str))
                    if row is None:
                        raise ApiError(404, "MENU_ITEM_NOT_FOUND", "Menu item was not found")
        return _row(row)

    @staticmethod
    def _price_item(item, selected):
        groups = item["options"] or []
        expected = {x.get("name"): x for x in groups}
        selected_map = {}
        for option in selected:
            if set(option) != {"group", "choice"} or option["group"] in selected_map:
                raise ApiError(422, "INVALID_MENU_OPTIONS", "Selected menu options are invalid")
            selected_map[option["group"]] = option["choice"]
        if set(selected_map) - set(expected):
            raise ApiError(422, "INVALID_MENU_OPTIONS", "Selected menu options are no longer available")
        delta = Decimal("0")
        for name, group in expected.items():
            choice_name = selected_map.get(name)
            if choice_name is None:
                if group.get("required"):
                    raise ApiError(422, "MENU_OPTION_REQUIRED", f"Choose an option for {name}")
                continue
            choice = next((x for x in group.get("choices", []) if x.get("name") == choice_name), None)
            if choice is None:
                raise ApiError(422, "INVALID_MENU_OPTIONS", "Selected menu options are no longer available")
            delta += Decimal(str(choice.get("price_delta_inr", 0)))
        price = Decimal(item["price_inr"]) + delta
        if price <= 0:
            raise ApiError(422, "INVALID_MENU_PRICE", "Selected options result in an invalid price")
        return price

    async def create_order(self, customer_id: UUID, payload: dict, key: str):
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("select pg_advisory_xact_lock(hashtext($1),hashtext($2))", str(customer_id), key)
                prior = await conn.fetchrow("""select id,request_fingerprint from public.restaurant_orders
                  where customer_id=$1 and idempotency_key=$2 for update""", customer_id, key)
                if prior:
                    if prior["request_fingerprint"] != fingerprint:
                        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This idempotency key was used for a different order")
                    return await self.get_order(customer_id, prior["id"], conn), False
                vendor = await conn.fetchrow("""select id from public.vendors where id=$1 and type='restaurant'
                  and is_active and is_verified for share""", payload["vendor_id"])
                if vendor is None:
                    raise ApiError(404, "RESTAURANT_NOT_FOUND", "Restaurant is unavailable")
                ids = [x["item_id"] for x in payload["items"]]
                items = await conn.fetch("""select id,vendor_id,category_id,name,description,price_inr,options,is_available
                  from public.restaurant_menu_items where id=any($1::uuid[]) and vendor_id=$2 for share""", ids, payload["vendor_id"])
                by_id = {x["id"]: x for x in items}
                if len(by_id) != len(ids):
                    raise ApiError(409, "MENU_CHANGED", "One or more selected menu items are no longer available")
                prepared = []
                total = Decimal("0")
                for line in payload["items"]:
                    item = dict(by_id[line["item_id"]])
                    if isinstance(item.get("options"), str):
                        item["options"] = json.loads(item["options"])
                    if not item["is_available"]:
                        raise ApiError(409, "MENU_ITEM_UNAVAILABLE", f"{item['name']} is currently unavailable")
                    unit = self._price_item(item, line["options"])
                    line_total = unit * line["quantity"]
                    total += line_total
                    prepared.append((item, line, unit, line_total))
                order = await conn.fetchrow("""insert into public.restaurant_orders
                  (customer_id,vendor_id,status,fulfillment_method,total_inr,idempotency_key,request_fingerprint)
                  values($1,$2,'payment_pending','pickup',$3,$4,$5) returning id""",
                  customer_id, payload["vendor_id"], total, key, fingerprint)
                for item, line, unit, line_total in prepared:
                    await conn.execute("""insert into public.restaurant_order_items
                      (order_id,item_id,item_name,description_snapshot,unit_price_inr,quantity,selected_options,line_total_inr)
                      values($1,$2,$3,$4,$5,$6,$7::jsonb,$8)""", order["id"], item["id"], item["name"], item["description"], unit, line["quantity"], json.dumps(line["options"]), line_total)
                await conn.execute("insert into public.restaurant_order_events(order_id,event_type,actor_id) values($1,'created',$2)", order["id"], customer_id)
                payment = await conn.fetchrow("""insert into public.restaurant_order_payments(order_id,amount_inr)
                  values($1,$2) returning id""", order["id"], total)
        return await self.get_order(customer_id, order["id"]), True

    async def get_order(self, customer_id, order_id, conn=None):
        if conn is None:
            async with self.pool.acquire() as acquired:
                return await self.get_order(customer_id, order_id, acquired)
        row = await conn.fetchrow("""select o.id,o.vendor_id,v.name as restaurant_name,o.status,o.fulfillment_method,
          o.total_inr,o.currency,o.created_at,p.status as payment_status,p.webhook_verified,
          pr.name as customer_name,pr.phone as customer_phone,
          coalesce(jsonb_agg(jsonb_build_object('item_id',i.item_id,'name',i.item_name,'description',i.description_snapshot,
          'unit_price_inr',i.unit_price_inr,'quantity',i.quantity,'selected_options',i.selected_options,
          'line_total_inr',i.line_total_inr) order by i.created_at) ,'[]'::jsonb) items,
          p.razorpay_order_id,p.amount_inr as payment_amount_inr,p.order_state
          from public.restaurant_orders o join public.vendors v on v.id=o.vendor_id
          join public.profiles pr on pr.id=o.customer_id
          left join public.restaurant_order_payments p on p.order_id=o.id
          left join public.restaurant_order_items i on i.order_id=o.id
          where o.id=$1 and o.customer_id=$2 group by o.id,v.name,p.id""", order_id, customer_id)
        return _row(row)

    async def attach_order(self, order_id, razorpay_order_id):
        async with self.pool.acquire() as conn:
            await conn.execute("update public.restaurant_order_payments set razorpay_order_id=$2,order_state='ready',updated_at=now() where order_id=$1", order_id, razorpay_order_id)

    async def mark_order_unknown(self, order_id):
        async with self.pool.acquire() as conn:
            await conn.execute("update public.restaurant_order_payments set order_state='reconciliation_required',updated_at=now() where order_id=$1", order_id)

    async def payment_for_order(self, order_id):
        async with self.pool.acquire() as conn:
            return _row(await conn.fetchrow("select * from public.restaurant_order_payments where order_id=$1", order_id))

    async def orders(self, customer_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""update public.restaurant_orders set status='payment_expired',updated_at=now()
              where customer_id=$1 and status='payment_pending' and payment_expires_at<=now()
                and exists(select 1 from public.restaurant_order_payments p where p.order_id=restaurant_orders.id and p.status='pending')""", customer_id)
            ids = await conn.fetch("select id from public.restaurant_orders where customer_id=$1 order by created_at desc limit 100", customer_id)
        return [await self.get_order(customer_id, x["id"]) for x in ids]

    async def vendor_orders(self, owner_id, vendor_id, admin=False):
        async with self.pool.acquire() as conn:
            if admin:
                rows = await conn.fetch("select id,customer_id from public.restaurant_orders where ($1::uuid is null or vendor_id=$1) order by created_at desc limit 200", vendor_id)
            else:
                await self._owned_restaurant(conn, owner_id, vendor_id)
                rows = await conn.fetch("select id,customer_id from public.restaurant_orders where vendor_id=$1 order by created_at desc limit 200", vendor_id)
        result = []
        for row in rows:
            item = await self.get_order(row["customer_id"], row["id"])
            if item:
                result.append(item)
        return result

    async def vendor_sales(self, owner_id, vendor_id):
        async with self.pool.acquire() as conn:
            await self._owned_restaurant(conn, owner_id, vendor_id)
            row = await conn.fetchrow("""select
              coalesce(sum(p.amount_inr) filter(where p.status='captured' and p.webhook_verified and p.updated_at>=date_trunc('day',now())),0) as today_gross_inr,
              coalesce(sum(p.amount_inr) filter(where p.status='captured' and p.webhook_verified and p.updated_at>=date_trunc('week',now())),0) as week_gross_inr,
              coalesce(sum(p.amount_inr) filter(where p.status='captured' and p.webhook_verified and p.updated_at>=date_trunc('month',now())),0) as month_gross_inr,
              count(o.id) as total_orders,
              count(o.id) filter(where p.status='captured' and p.webhook_verified) as paid_orders
              from public.restaurant_orders o join public.restaurant_order_payments p on p.order_id=o.id
              where o.vendor_id=$1""", vendor_id)
        return _row(row) or {}

    async def transition(self, owner_id, vendor_id, order_id, status):
        allowed = {"placed": {"accepted"}, "accepted": {"preparing"}, "preparing": {"ready"}, "ready": {"completed"}}
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await self._owned_restaurant(conn, owner_id, vendor_id)
                row = await conn.fetchrow("""select o.customer_id,o.status,p.status as payment_status,p.webhook_verified
                  from public.restaurant_orders o join public.restaurant_order_payments p on p.order_id=o.id
                  where o.id=$1 and o.vendor_id=$2 for update of o,p""", order_id, vendor_id)
                if row is None:
                    raise ApiError(404, "ORDER_NOT_FOUND", "Restaurant order was not found")
                if row["payment_status"] != "captured" or not row["webhook_verified"]:
                    raise ApiError(409, "ORDER_PAYMENT_UNVERIFIED", "Vendor fulfillment requires a payment-confirmed order")
                if status not in allowed.get(row["status"], set()):
                    raise ApiError(409, "INVALID_ORDER_TRANSITION", "This order status transition is not allowed")
                await conn.execute("update public.restaurant_orders set status=$2,updated_at=now() where id=$1", order_id, status)
                await conn.execute("insert into public.restaurant_order_events(order_id,event_type,actor_id) values($1,$2,$3)", order_id, status, owner_id)
                customer = row["customer_id"]
        return await self.get_order(customer, order_id)

    async def process_payment_webhook(self, order_id, payment_id, amount_paise, currency, captured):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                payment = await conn.fetchrow("select * from public.restaurant_order_payments where razorpay_order_id=$1", order_id)
                if payment is None:
                    return False
                order = await conn.fetchrow("select * from public.restaurant_orders where id=$1 for update", payment["order_id"])
                row = await conn.fetchrow("select * from public.restaurant_order_payments where id=$1 for update", payment["id"])
                if order is None or row is None or row["razorpay_order_id"] != order_id:
                    return False
                if row["razorpay_payment_id"] not in (None, payment_id) or row["currency"].strip().upper() != currency.strip().upper():
                    raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
                if int(Decimal(row["amount_inr"]) * 100) != amount_paise:
                    raise ApiError(400, "PAYMENT_AMOUNT_MISMATCH", "Webhook payment could not be verified")
                dupe = await conn.fetchval("select exists(select 1 from public.restaurant_order_payments where razorpay_payment_id=$1 and id<>$2)", payment_id, row["id"])
                if dupe:
                    raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
                if row["status"] in ("captured", "refunded") or (row["status"] == "failed" and not captured):
                    if row["razorpay_payment_id"] is None:
                        raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
                    return True
                await conn.execute("update public.restaurant_order_payments set status=$2,webhook_verified=true,razorpay_payment_id=$3,updated_at=now() where id=$1", row["id"], "captured" if captured else "failed", payment_id)
                payment_hold_active = order["payment_expires_at"] > datetime.now(timezone.utc)
                next_status = "placed" if captured and order["status"] == "payment_pending" and payment_hold_active else "refund_review_required" if captured else "payment_failed"
                await conn.execute("update public.restaurant_orders set status=$2,updated_at=now() where id=$1 and status='payment_pending'", order["id"], next_status)
                event = "payment_captured" if next_status == "placed" else "late_payment_capture_refund_review_required" if captured else "payment_failed"
                if captured and order["status"] != "payment_pending":
                    await conn.execute("update public.restaurant_orders set status='refund_review_required',updated_at=now() where id=$1", order["id"])
                await conn.execute("insert into public.restaurant_order_events(order_id,event_type) values($1,$2)", order["id"], event)
                return True
