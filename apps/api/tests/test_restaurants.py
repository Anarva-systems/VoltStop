import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ApiError
from app.restaurants.repository import RestaurantRepository
from app.restaurants.schemas import MenuItemCreate, OrderCreate


class _MenuAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_):
        return False


class _EmptyMenuConnection:
    def __init__(self, owner_exists=True):
        self.owner_exists = owner_exists

    async def fetchrow(self, query, *_):
        assert "type='restaurant'" in query
        return {"id": uuid4(), "name": "Published Dhaba", "type": "restaurant"}

    async def fetch(self, query, *_):
        assert "restaurant_menu_categories" in query or "restaurant_orders where customer_id" in query
        return []

    async def fetchval(self, query, *_):
        assert "owner_id=$2" in query
        return self.owner_exists

    async def execute(self, *_):
        return "UPDATE 0"


class _EmptyMenuPool:
    def __init__(self, owner_exists=True):
        self.connection = _EmptyMenuConnection(owner_exists)

    def acquire(self):
        return _MenuAcquire(self.connection)


def test_published_restaurant_without_menu_returns_empty_categories():
    menu = asyncio.run(RestaurantRepository(_EmptyMenuPool()).menu(uuid4()))

    assert menu is not None
    assert menu["vendor"]["type"] == "restaurant"
    assert menu["categories"] == []


def test_vendor_cannot_read_another_restaurants_menu():
    repository = RestaurantRepository(_EmptyMenuPool(owner_exists=False))

    with pytest.raises(ApiError) as error:
        asyncio.run(repository.vendor_menu(uuid4(), uuid4()))

    assert error.value.status_code == 404
    assert error.value.detail["code"] == "RESTAURANT_NOT_FOUND"


def test_empty_customer_order_history_returns_empty_list():
    repository = RestaurantRepository(_EmptyMenuPool())

    assert asyncio.run(repository.orders(uuid4())) == []


def test_menu_item_schema_rejects_duplicate_or_malformed_options():
    category = uuid4()
    with pytest.raises(ValidationError):
        MenuItemCreate(category_id=category, name="Tea", price_inr=30, options=[
            {"name": "Size", "required": True, "choices": [{"name": "Small"}]},
            {"name": "Size", "choices": [{"name": "Large"}]},
        ])
    with pytest.raises(ValidationError):
        MenuItemCreate(category_id=category, name="Tea", price_inr=30, options=[
            {"name": "Size", "required": True, "choices": []},
        ])


def test_order_schema_rejects_duplicate_menu_ids_and_unsupported_fulfillment():
    item_id = uuid4()
    with pytest.raises(ValidationError):
        OrderCreate(vendor_id=uuid4(), items=[{"item_id": item_id}, {"item_id": item_id}])
    with pytest.raises(ValidationError):
        OrderCreate(vendor_id=uuid4(), fulfillment_method="delivery", items=[{"item_id": uuid4()}])


def test_server_prices_selected_options_and_rejects_unknown_or_missing_choices():
    item = {"price_inr": Decimal("100.00"), "options": [
        {"name": "Size", "required": True, "choices": [
            {"name": "Regular", "price_delta_inr": 0}, {"name": "Large", "price_delta_inr": "35.00"},
        ]},
        {"name": "Spice", "required": False, "choices": [{"name": "Mild", "price_delta_inr": 0}]},
    ]}
    assert RestaurantRepository._price_item(item, [{"group": "Size", "choice": "Large"}]) == Decimal("135.00")
    with pytest.raises(ApiError):
        RestaurantRepository._price_item(item, [])
    with pytest.raises(ApiError):
        RestaurantRepository._price_item(item, [{"group": "Size", "choice": "Not a size"}])


class _Transaction:
    def __init__(self, connection): self.connection = connection
    async def __aenter__(self): await self.connection.lock.acquire()
    async def __aexit__(self, *_): self.connection.lock.release()


class _Acquire:
    def __init__(self, connection): self.connection = connection
    async def __aenter__(self): return self.connection
    async def __aexit__(self, *_): return False


class _OrderConnection:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.vendor_id, self.customer_id, self.item_id = uuid4(), uuid4(), uuid4()
        self.order = None
        self.payment = None
        self.lines = []
        self.order_writes = 0
        self.item_available = True

    def transaction(self): return _Transaction(self)
    async def execute(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "pg_advisory_xact_lock" in normalized or "insert into public.restaurant_order_events" in normalized:
            return "SELECT 1"
        if "insert into public.restaurant_order_items" in normalized:
            self.lines.append({"item_id": args[1], "name": args[2], "description": args[3],
                               "unit_price": args[4], "quantity": args[5], "options": args[6], "line_total": args[7]})
            return "INSERT 0 1"
        raise AssertionError(f"Unexpected execute: {normalized}")

    async def fetchrow(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "select id,request_fingerprint from public.restaurant_orders" in normalized:
            return {"id": self.order["id"], "request_fingerprint": self.order["fingerprint"]} if self.order and args == (self.customer_id, self.order["key"]) else None
        if "from public.vendors where id=$1 and type='restaurant'" in normalized:
            return {"id": self.vendor_id} if args[0] == self.vendor_id else None
        if "insert into public.restaurant_orders" in normalized:
            self.order_writes += 1
            self.order = {"id": uuid4(), "customer": args[0], "vendor": args[1], "total": args[2], "key": args[3], "fingerprint": args[4], "status": "payment_pending"}
            return {"id": self.order["id"]}
        if "insert into public.restaurant_order_payments" in normalized:
            self.payment = {"id": uuid4(), "order_id": args[0], "amount_inr": args[1], "currency": "INR", "status": "pending", "webhook_verified": False, "order_state": "creating", "razorpay_order_id": None}
            return {"id": self.payment["id"]}
        if "from public.restaurant_orders o join public.vendors" in normalized:
            return {"id": self.order["id"], "vendor_id": self.order["vendor"], "restaurant_name": "Demo Restaurant",
                    "status": self.order["status"], "fulfillment_method": "pickup", "total_inr": self.order["total"],
                    "currency": "INR", "customer_name": "Customer", "customer_phone": None,
                    "payment_status": self.payment["status"], "webhook_verified": self.payment["webhook_verified"],
                    "razorpay_order_id": self.payment["razorpay_order_id"], "amount_inr": self.payment["amount_inr"],
                    "order_state": self.payment["order_state"], "items": self.lines}
        if "from public.restaurant_order_payments where order_id=$1" in normalized:
            return self.payment if self.payment and args[0] == self.payment["order_id"] else None
        raise AssertionError(f"Unexpected fetchrow: {normalized}")

    async def fetch(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.restaurant_menu_items where id=any" in normalized:
            return [{"id": self.item_id, "vendor_id": self.vendor_id, "category_id": uuid4(), "name": "Masala Dosa",
                     "description": "Freshly prepared", "price_inr": Decimal("100.00"),
                     "options": json.dumps([{"name": "Size", "required": True, "choices": [
                         {"name": "Regular", "price_delta_inr": 0}, {"name": "Large", "price_delta_inr": "35.00"}]}]),
                     "is_available": self.item_available}] if args[0] == [self.item_id] else []
        raise AssertionError(f"Unexpected fetch: {normalized}")


class _OrderPool:
    def __init__(self): self.connection = _OrderConnection()
    def acquire(self): return _Acquire(self.connection)


def test_order_creation_calculates_price_snapshots_and_replays_idempotently():
    async def run():
        pool = _OrderPool()
        customer = pool.connection.customer_id
        repository = RestaurantRepository(pool)
        values = {"vendor_id": pool.connection.vendor_id, "fulfillment_method": "pickup", "items": [
            {"item_id": pool.connection.item_id, "quantity": 2, "options": [{"group": "Size", "choice": "Large"}]},
        ]}
        (first, created), (replay, replay_created) = await asyncio.gather(
            repository.create_order(customer, values, "restaurant-order-key"),
            repository.create_order(customer, values, "restaurant-order-key"),
        )
        assert created is True and replay_created is False
        assert first["id"] == replay["id"]
        assert first["total_inr"] == Decimal("270.00")
        assert pool.connection.order_writes == 1
        assert pool.connection.lines[0]["unit_price"] == Decimal("135.00")
    asyncio.run(run())


class _WebhookConnection:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.order_id, self.payment_id, self.payment_ref = uuid4(), uuid4(), "pay_restaurant_test"
        self.payment = {"id": self.payment_id, "order_id": self.order_id, "razorpay_order_id": "order_restaurant_test",
                        "razorpay_payment_id": None, "amount_inr": Decimal("135.00"), "currency": "INR", "status": "pending"}
        self.order = {"id": self.order_id, "status": "payment_pending", "payment_expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)}

    def transaction(self): return _Transaction(self)
    async def fetchrow(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "from public.restaurant_order_payments where razorpay_order_id=$1" in normalized:
            return self.payment if args[0] == "order_restaurant_test" else None
        if "from public.restaurant_orders where id=$1 for update" in normalized:
            return dict(self.order) if args[0] == self.order_id else None
        if "from public.restaurant_order_payments where id=$1 for update" in normalized:
            return self.payment if args[0] == self.payment_id else None
        raise AssertionError(f"Unexpected webhook fetchrow: {normalized}")
    async def fetchval(self, query, *_):
        assert "razorpay_payment_id" in query
        return False
    async def execute(self, query, *args):
        normalized = " ".join(query.lower().split())
        if "update public.restaurant_order_payments set status=$2" in normalized:
            self.payment.update(status=args[1], webhook_verified=True, razorpay_payment_id=args[2])
        elif "update public.restaurant_orders set status=$2" in normalized:
            self.order["status"] = args[1]
        elif "update public.restaurant_orders set status='refund_review_required'" in normalized:
            self.order["status"] = "refund_review_required"
        elif "insert into public.restaurant_order_events" in normalized:
            pass
        else:
            raise AssertionError(f"Unexpected webhook execute: {normalized}")
        return "UPDATE 1"


class _WebhookPool:
    def __init__(self): self.connection = _WebhookConnection()
    def acquire(self): return _Acquire(self.connection)


def test_payment_webhook_is_amount_verified_idempotent_and_authorizes_order_placement():
    async def run():
        pool = _WebhookPool()
        repo = RestaurantRepository(pool)
        args = ("order_restaurant_test", pool.connection.payment_ref, 13500, "INR", True)
        assert await repo.process_payment_webhook(*args) is True
        assert pool.connection.order["status"] == "placed"
        assert pool.connection.payment["status"] == "captured"
        assert pool.connection.payment["webhook_verified"] is True
        assert await repo.process_payment_webhook(*args) is True
        with pytest.raises(ApiError):
            await repo.process_payment_webhook("order_restaurant_test", pool.connection.payment_ref, 13501, "INR", True)
    asyncio.run(run())


def test_order_idempotency_key_cannot_change_payload_and_unavailable_item_is_rejected():
    async def run():
        pool = _OrderPool()
        customer, repository = pool.connection.customer_id, RestaurantRepository(pool)
        base = {"vendor_id": pool.connection.vendor_id, "fulfillment_method": "pickup", "items": [
            {"item_id": pool.connection.item_id, "quantity": 1, "options": [{"group": "Size", "choice": "Regular"}]},
        ]}
        await repository.create_order(customer, base, "restaurant-order-key")
        changed = {**base, "items": [{**base["items"][0], "quantity": 2}]}
        with pytest.raises(ApiError) as mismatch:
            await repository.create_order(customer, changed, "restaurant-order-key")
        assert mismatch.value.status_code == 409
        pool = _OrderPool()
        pool.connection.item_available = False
        unavailable_values = {"vendor_id": pool.connection.vendor_id, "fulfillment_method": "pickup", "items": [
            {"item_id": pool.connection.item_id, "quantity": 1, "options": [{"group": "Size", "choice": "Regular"}]},
        ]}
        with pytest.raises(ApiError) as unavailable:
            await RestaurantRepository(pool).create_order(pool.connection.customer_id, unavailable_values, "another-order-key")
        assert unavailable.value.status_code == 409
        assert pool.connection.order_writes == 0
    asyncio.run(run())
