import json
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.service import verify_supabase_access_token
from app.core.config import get_settings
from app.core.database_dependency import get_database
from app.core.dependencies import get_redis
from app.core.errors import ApiError
from app.core.models import AuthenticatedUser
from app.main import app, settings as app_settings
from app.payments.service import verify_webhook_signature
from app.bookings.router import payment_gateway
from app.routes.service import PilotRouteService, RouteResult
from app.routes.router import route_service
from app.finance.consistency import check_financial_consistency
from app.finance.refunds import validate_refund_amount
from app.admin.repository import AdminRepository
from app.admin.portal_pages import customers
from pathlib import Path

USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
OTHER_USER_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
VENDOR_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
SLOT_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")



class FakeDatabase:
    def __init__(self) -> None:
        self.slot_record = {
            "id": SLOT_ID,
            "vendor_id": VENDOR_ID,
            "slot_start_time": datetime.now(timezone.utc) + timedelta(days=1),
            "slot_end_time": datetime.now(timezone.utc) + timedelta(days=1, hours=1),
            "capacity": 2,
            "price_inr": Decimal("350.00"),
            "status": "available",
        }
        self.profile_record = {
            "id": USER_ID,
            "phone": "+919999999999",
            "name": "Driver",
            "car_model": "Demo EV",
            "battery_kwh": Decimal("60.00"),
            "default_efficiency_km_per_kwh": Decimal("6.000"),
            "current_soc": Decimal("72.50"),
        }
        self.booking_record = None
        self.force_booking_conflict = False
        self.payment_webhook_events = []
        self.vendor_scope_calls = []
        self.refund_webhook = None
        self.dispute_rows = {}
        self.dispute_idempotency = {}
        self.dispute_booking = {
            "id": uuid4(), "user_id": USER_ID, "vendor_id": VENDOR_ID, "status": "confirmed",
            "payment_id": uuid4(), "payment_status": "captured", "webhook_verified": True,
            "amount_inr": Decimal("350.00"),
        }
        self.saved_routes = []
        self.vehicle_rows = {}
        self.vehicle_idempotency = {}
        self.pool = FakeAdminPool()

    async def vendor_id_for_owner(self, owner_id):
        return VENDOR_ID if owner_id == USER_ID else None

    async def vendor_bookings(self, owner_id, vendor_id, status=None):
        self.vendor_scope_calls.append(("bookings", owner_id, vendor_id, status))
        return []

    async def vendor_booking(self, owner_id, vendor_id, booking_id):
        self.vendor_scope_calls.append(("booking", owner_id, vendor_id, booking_id))
        return None

    async def profile(self, user_id):
        return self.profile_record if user_id == USER_ID else None

    async def patch_profile(self, user_id, updates):
        if user_id != USER_ID:
            return None
        self.profile_record.update(updates)
        return self.profile_record

    async def driver_vehicles(self, user_id):
        return list(self.vehicle_rows.get(user_id, {}).values())

    async def driver_vehicle(self, user_id, vehicle_id):
        return self.vehicle_rows.get(user_id, {}).get(vehicle_id)

    async def create_driver_vehicle(self, user_id, values, idempotency_key):
        replay = self.vehicle_idempotency.get((user_id, idempotency_key))
        if replay is not None:
            if replay["make"] != values["make"] or replay["model"] != values["model"]:
                raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "This key was used for another vehicle")
            return replay
        rows = self.vehicle_rows.setdefault(user_id, {})
        is_default = bool(values.get("is_default")) or not any(row["is_default"] for row in rows.values())
        if is_default:
            for row in rows.values(): row["is_default"] = False
        row = {**values, "id": uuid4(), "user_id": user_id, "is_default": is_default}
        rows[row["id"]] = row
        self.vehicle_idempotency[(user_id, idempotency_key)] = row
        return row

    async def patch_driver_vehicle(self, user_id, vehicle_id, changes):
        row = self.vehicle_rows.get(user_id, {}).get(vehicle_id)
        if row is None: return None
        if changes.get("is_default"):
            for item in self.vehicle_rows[user_id].values(): item["is_default"] = False
        row.update(changes)
        return row

    async def select_default_driver_vehicle(self, user_id, vehicle_id):
        row = self.vehicle_rows.get(user_id, {}).get(vehicle_id)
        if row is None: return None
        for item in self.vehicle_rows[user_id].values(): item["is_default"] = False
        row["is_default"] = True
        return row

    async def delete_driver_vehicle(self, user_id, vehicle_id):
        row = self.vehicle_rows.get(user_id, {}).pop(vehicle_id, None)
        if row is None: return False
        if row["is_default"] and self.vehicle_rows[user_id]:
            next(iter(self.vehicle_rows[user_id].values()))["is_default"] = True
        return True

    async def save_driver_route(self, user_id, request, route):
        route_id = uuid4()
        self.saved_routes.append((user_id, request, route, route_id))
        return route_id

    async def nearby_vendors(self, lat, lng, radius_km):
        return [{"vendor": {"id": str(VENDOR_ID), "name": "Demo Dhaba", "type": "restaurant"}, "distance_km": 4.2,
                 "services": [], "availability": []}]

    async def vendor(self, vendor_id):
        if vendor_id != VENDOR_ID:
            return None
        return {"vendor": {"id": str(VENDOR_ID), "name": "Demo Dhaba"}, "services": [], "availability": []}

    async def vendor_slots(self, vendor_id):
        return [self.slot_record] if vendor_id == VENDOR_ID else None

    async def slot(self, slot_id):
        return self.slot_record if slot_id == SLOT_ID and self.slot_record["status"] == "available" else None

    async def recommended_route_vendors(self, route_geojson):
        return [{"vendor": {"id": str(VENDOR_ID)}, "distance_km": 2.0}]

    async def create_pending_booking(self, user_id, slot_id, booking_id, order_id, expected_amount):
        if self.force_booking_conflict:
            raise ApiError(409, "SLOT_UNAVAILABLE", "Slot is no longer available")
        self.booking_record = {
            "id": booking_id,
            "user_id": user_id,
            "vendor_id": VENDOR_ID,
            "slot_id": slot_id,
            "payment_id": uuid4(),
            "amount_paid": Decimal("0.00"),
            "status": "pending",
            "razorpay_order_id": order_id,
            "razorpay_payment_id": None,
            "amount_inr": Decimal("350.00"),
            "currency": "INR",
            "payment_status": "pending",
        }
        return self.booking_record

    async def bookings(self, user_id, limit, offset):
        if self.booking_record and self.booking_record["user_id"] == user_id:
            return [self.booking_record][offset:offset + limit]
        return []

    async def booking(self, user_id, booking_id):
        if self.booking_record and self.booking_record["id"] == booking_id:
            if self.booking_record["user_id"] != user_id:
                raise ApiError(403, "FORBIDDEN", "You cannot access this booking")
            return self.booking_record
        return None

    async def cancel_booking(self, user_id, booking_id):
        booking = await self.booking(user_id, booking_id)
        if booking is None:
            return None
        if booking["status"] != "pending":
            raise ApiError(409, "BOOKING_NOT_CANCELLABLE", "Only pending bookings can be cancelled")
        booking["status"] = "cancelled"
        return booking

    async def process_payment_webhook(self, order_id, payment_id, amount_paise, currency, captured):
        booking = self.booking_record
        if not booking or booking["razorpay_order_id"] != order_id:
            return False
        if booking["razorpay_payment_id"] is not None and booking["razorpay_payment_id"] != payment_id:
            raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
        if currency != booking["currency"]:
            raise ApiError(400, "PAYMENT_WEBHOOK_REJECTED", "Webhook payment could not be verified")
        if amount_paise != int(booking["amount_inr"] * 100):
            raise ApiError(400, "PAYMENT_AMOUNT_MISMATCH", "Webhook payment could not be verified")
        if booking["payment_status"] in ("captured", "refunded"):
            return True
        if booking["payment_status"] == "failed" and not captured:
            return True
        booking["razorpay_payment_id"] = payment_id
        booking["payment_status"] = "captured" if captured else "failed"
        self.payment_webhook_events.append("payment_success" if captured else "payment_failed")
        if captured and booking["status"] == "pending":
            booking["status"] = "confirmed"
            booking["amount_paid"] = booking["amount_inr"]
            self.payment_webhook_events.append("confirmed")
        elif not captured and booking["status"] == "pending":
            booking["status"] = "expired"
            self.payment_webhook_events.append("expired")
        return True

    async def process_refund_webhook(self, refund_id, payment_id, amount_paise, currency, provider_status, local_refund_id=None):
        self.refund_webhook = (refund_id, payment_id, amount_paise, currency, provider_status, local_refund_id)
        return True

    async def create_customer_dispute(self, customer_id, booking_id, reason, description, idempotency_key, request_metadata=None):
        if idempotency_key in self.dispute_idempotency:
            return self.dispute_rows[self.dispute_idempotency[idempotency_key]], False
        booking = self.dispute_booking
        if booking["id"] != booking_id or booking["user_id"] != customer_id:
            raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
        if (booking["status"] not in ("confirmed", "completed", "cancelled")
                or booking["payment_status"] not in ("captured", "refunded") or not booking["webhook_verified"]):
            raise ApiError(409, "BOOKING_NOT_ELIGIBLE_FOR_DISPUTE", "Booking is not eligible")
        if any(row["booking_id"] == booking_id and row["status"] in ("open", "investigating", "awaiting_customer", "awaiting_vendor") for row in self.dispute_rows.values()):
            raise ApiError(409, "ACTIVE_DISPUTE_EXISTS", "Active dispute exists")
        dispute_id = uuid4()
        row = {"id": dispute_id, "booking_id": booking_id, "customer_id": customer_id,
               "vendor_id": booking["vendor_id"], "amount_inr": booking["amount_inr"], "reason": reason,
               "description": description, "status": "open", "timeline": []}
        self.dispute_rows[dispute_id] = row
        self.dispute_idempotency[idempotency_key] = dispute_id
        return row, True

    async def customer_disputes(self, customer_id, limit, offset):
        rows = [row for row in self.dispute_rows.values() if row["customer_id"] == customer_id]
        return {"items": rows[offset:offset + limit], "total": len(rows), "limit": limit, "offset": offset}

    async def customer_dispute(self, customer_id, dispute_id):
        row = self.dispute_rows.get(dispute_id)
        return row if row and row["customer_id"] == customer_id else None

    async def vendor_disputes(self, vendor_id, limit, offset):
        rows = [row for row in self.dispute_rows.values() if row["vendor_id"] == vendor_id]
        return {"items": rows[offset:offset + limit], "total": len(rows), "limit": limit, "offset": offset}

    async def vendor_dispute(self, vendor_id, dispute_id):
        row = self.dispute_rows.get(dispute_id)
        return row if row and row["vendor_id"] == vendor_id else None

    async def add_customer_dispute_message(self, customer_id, dispute_id, message, idempotency_key, request_metadata=None):
        row = await self.customer_dispute(customer_id, dispute_id)
        if row is None:
            raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
        row["timeline"].append({"actor_type": "customer", "event_type": "customer_message", "message": message})
        return row

    async def add_vendor_dispute_message(self, vendor_id, actor_id, dispute_id, message, idempotency_key, request_metadata=None):
        row = await self.vendor_dispute(vendor_id, dispute_id)
        if row is None:
            raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
        row["timeline"].append({"actor_type": "vendor", "event_type": "vendor_message", "message": message})
        return row


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def eval(self, _script, _count, key, expected):
        if self.values.get(key) == expected:
            del self.values[key]
            return 1
        return 0


class FakeAdminPool:
    def __init__(self):
        self.identity_record = None
        self.vendor_state = {"id": VENDOR_ID, "name": "Test Vendor", "is_active": False,
                             "is_verified": False, "status": "pending"}
        self.audit_rows = 0

    def acquire(self):
        return self

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def fetchrow(self, query, *args):
        if "from public.admin_users u" in query and self.identity_record:
            if self.identity_record["user_id"] == args[0]:
                return self.identity_record
        if "for update of v" in query and "from public.vendors v" in query:
            return dict(self.vendor_state)
        if "from public.vendors v" in query and "where v.id=$1" in query:
            return {"id": VENDOR_ID, "name": "Test Vendor", "type": "hotel", "services": [], "bookings": 0}
        return None

    async def execute(self, query, *args):
        if query.startswith("update public.vendors set is_active"):
            self.vendor_state.update({"is_active": args[1], "is_verified": args[2]})
        elif query.startswith("insert into public.vendor_onboarding"):
            self.vendor_state["status"] = args[1]
        elif query.startswith("insert into public.admin_audit_logs"):
            self.audit_rows += 1
        return "OK"


class FakeRefundConnection:
    def __init__(self):
        self.booking_id = uuid4()
        self.payment_id = uuid4()
        self.booking = {"id": self.booking_id, "status": "confirmed", "vendor_id": VENDOR_ID,
                        "payment_id": self.payment_id, "amount_inr": Decimal("500.00"),
                        "payment_status": "captured", "webhook_verified": True,
                        "razorpay_payment_id": "pay_test_123"}
        self.refunds = []
        self.audit_count = 0

    def acquire(self): return self
    def transaction(self): return self
    async def __aenter__(self): return self
    async def __aexit__(self, *_args): return None

    async def fetchrow(self, query, *args):
        if "from public.bookings b join public.payments p" in query:
            return self.booking if args[0] == self.booking_id else None
        if "where r.idempotency_key=$1" in query:
            row = next((item for item in self.refunds if item["idempotency_key"] == args[0]), None)
            return {**row, "razorpay_payment_id": "pay_test_123"} if row else None
        if "insert into public.refunds" in query:
            row = {"id": uuid4(), "booking_id": args[0], "payment_id": args[1], "requested_by": args[2],
                   "amount_inr": args[3], "reason": args[4], "status": "requested", "idempotency_key": args[5],
                   "dispute_id": args[6]}
            self.refunds.append(row)
            return row
        return None

    async def fetchval(self, query, *args):
        if "coalesce(sum(amount_inr),0)" in query:
            return sum((row["amount_inr"] for row in self.refunds if row["status"] not in ("failed", "rejected")), Decimal("0"))
        if "select exists" in query and "public.refunds" in query:
            return any(row["payment_id"] == args[0] and row["status"] in ("requested", "approved", "processing") for row in self.refunds)
        return None

    async def execute(self, query, *args):
        if query.startswith("insert into public.admin_audit_logs"):
            self.audit_count += 1
        return "OK"


class FakeRefundPool:
    def __init__(self): self.connection = FakeRefundConnection()
    def acquire(self): return self.connection


class FakeGateway:
    async def create_order(self, booking_id, amount):
        return {"order_id": "order_test_123", "amount_paise": int(amount * 100), "currency": "INR", "key_id": "rzp_test_public"}


@pytest.fixture

def context():
    app.dependency_overrides.clear()
    database = FakeDatabase()
    redis = FakeRedis()
    user = AuthenticatedUser(id=USER_ID, email="driver@example.test", phone=None,
                             user_metadata={}, app_metadata={})

    async def current_user():
        return user

    async def fake_database():
        return database

    async def fake_redis():
        return redis

    async def fake_gateway():
        return FakeGateway()

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_database] = fake_database
    app.dependency_overrides[get_redis] = fake_redis
    app.dependency_overrides[payment_gateway] = fake_gateway
    old_database_url = app_settings.database_url
    old_redis_enabled = app_settings.redis_enabled
    app_settings.database_url = ""
    app_settings.redis_enabled = False
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, database=database, redis=redis, user=user)
    finally:
        app_settings.database_url = old_database_url
        app_settings.redis_enabled = old_redis_enabled
        app.dependency_overrides.clear()


def test_auth_me_uses_authenticated_user(context):
    response = context.client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(USER_ID)


def test_auth_me_requires_bearer_token(context):
    override = app.dependency_overrides.pop(get_current_user)
    try:
        response = context.client.get("/api/v1/auth/me")
        assert response.status_code == 401
        assert response.json()["success"] is False
    finally:
        app.dependency_overrides[get_current_user] = override


def test_new_portal_apis_remain_behind_bearer_authentication(context):
    override = app.dependency_overrides.pop(get_current_user)
    try:
        paths = [
            "/api/v1/admin/customers", "/api/v1/admin/availability", "/api/v1/admin/services",
            "/api/v1/admin/pricing", "/api/v1/admin/support", "/api/v1/admin/settings",
            "/api/v1/admin/notifications", "/api/v1/notifications", "/api/v1/support",
            f"/api/v1/restaurants/{VENDOR_ID}/menu", "/api/v1/restaurants/orders",
        ]
        for path in paths:
            response = context.client.get(path)
            assert response.status_code == 401, (path, response.text)
    finally:
        app.dependency_overrides[get_current_user] = override


def test_customer_directory_supports_neon_without_supabase_auth_schema():
    class Connection:
        def __init__(self):
            self.directory_query = ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def fetchval(self, query, *_args):
            return False if "to_regclass('auth.users')" in query else 1

        async def fetch(self, query, *_args):
            self.directory_query = query
            return [{"id": USER_ID, "name": "Driver", "email": "driver@example.test", "phone": None,
                     "created_at": datetime.now(timezone.utc), "account_status": "unknown",
                     "booking_count": 0, "complaint_count": 0}]

    class Pool:
        def __init__(self):
            self.connection = Connection()

        def acquire(self):
            return self.connection

    pool = Pool()
    result = asyncio.run(customers(
        _admin=None, database=SimpleNamespace(pool=pool), q=None, status=None, limit=50, offset=0,
    ))
    assert result["success"] is True
    assert result["data"]["total"] == 1
    assert result["data"]["items"][0]["account_status"] == "unknown"
    assert "auth.users" not in pool.connection.directory_query


def test_hotel_discovery_requires_authenticated_customer(context):
    override = app.dependency_overrides.pop(get_current_user)
    try:
        response = context.client.get("/api/v1/hotels/rooms")
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = override


def test_vendor_hotel_room_management_requires_authenticated_vendor(context):
    override = app.dependency_overrides.pop(get_current_user)
    try:
        response = context.client.get("/api/v1/vendor/hotels/rooms")
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = override


def test_driver_cannot_review_hotel_refunds(context):
    response = context.client.get("/api/v1/admin/hotel-refunds")
    assert response.status_code == 403


def test_supabase_token_verification_uses_auth_user_endpoint():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/auth/v1/user")
        assert request.headers["authorization"] == "Bearer signed-token-value"
        return httpx.Response(200, json={"id": str(USER_ID), "email": "a@b.test"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            settings = get_settings().model_copy(update={
                "supabase_url": "https://example.supabase.co",
                "supabase_anon_key": "anon-test",
            })
            user = await verify_supabase_access_token("signed-token-value", client, settings)
            assert user.id == USER_ID

    import asyncio
    asyncio.run(run())


def test_invalid_supabase_token_is_401():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid token"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            settings = get_settings().model_copy(update={
                "supabase_url": "https://example.supabase.co",
                "supabase_anon_key": "anon-test",
            })
            with pytest.raises(ApiError) as error:
                await verify_supabase_access_token("invalid-signed-token", client, settings)
            assert error.value.status_code == 401

    import asyncio
    asyncio.run(run())


def test_vehicle_crud_is_authenticated_and_owner_scoped(context):
    payload = {
        "make": "Tata", "model": "Nexon EV", "vehicle_type": "suv",
        "battery_kwh": 40.5, "efficiency_km_per_kwh": 6.1,
        "current_soc": 63, "connector_compatibility": ["CCS2"],
    }
    created = context.client.post("/api/v1/vehicles", json=payload,
                                  headers={"Idempotency-Key": "vehicle-create-key-001"})
    assert created.status_code == 200
    vehicle_id = created.json()["data"]["id"]
    assert created.json()["data"]["is_default"] is True
    assert created.json()["data"]["current_soc"] == 63
    assert context.client.get("/api/v1/vehicles").json()["data"][0]["id"] == vehicle_id
    assert context.client.get(f"/api/v1/vehicles/{vehicle_id}").status_code == 200

    updated = context.client.patch(f"/api/v1/vehicles/{vehicle_id}", json={"current_soc": 54})
    assert updated.status_code == 200
    assert updated.json()["data"]["current_soc"] == 54

    override = app.dependency_overrides.pop(get_current_user)
    async def other_user():
        return AuthenticatedUser(id=OTHER_USER_ID)
    app.dependency_overrides[get_current_user] = other_user
    try:
        assert context.client.get(f"/api/v1/vehicles/{vehicle_id}").status_code == 404
        assert context.client.patch(f"/api/v1/vehicles/{vehicle_id}", json={"model": "attacker"}).status_code == 404
        assert context.client.delete(f"/api/v1/vehicles/{vehicle_id}").status_code == 404
        assert context.client.get("/api/v1/vehicles").json()["data"] == []
    finally:
        app.dependency_overrides[get_current_user] = override

    assert context.client.delete(f"/api/v1/vehicles/{vehicle_id}").json()["data"]["deleted"] is True


def test_vehicle_create_requires_idempotency_and_validates_data(context):
    payload = {"make": "Tata", "model": "EV", "battery_kwh": 40, "efficiency_km_per_kwh": 6}
    assert context.client.post("/api/v1/vehicles", json=payload).status_code == 400
    assert context.client.post("/api/v1/vehicles", json={**payload, "battery_kwh": 0},
                               headers={"Idempotency-Key": "vehicle-invalid-key"}).status_code == 422


def test_vehicle_create_is_idempotent_and_default_selection_is_per_user(context):
    payload = {"make": "Tata", "model": "EV", "battery_kwh": 40, "efficiency_km_per_kwh": 6}
    headers = {"Idempotency-Key": "vehicle-create-key-002"}
    first = context.client.post("/api/v1/vehicles", json=payload, headers=headers)
    replay = context.client.post("/api/v1/vehicles", json=payload, headers=headers)
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    second = context.client.post("/api/v1/vehicles", json={**payload, "model": "Second"},
                                 headers={"Idempotency-Key": "vehicle-create-key-003"})
    assert second.status_code == 200
    assert second.json()["data"]["is_default"] is False
    selected = context.client.post(f"/api/v1/vehicles/{second.json()['data']['id']}/default")
    assert selected.status_code == 200 and selected.json()["data"]["is_default"] is True
    assert sum(row["is_default"] for row in context.database.vehicle_rows[USER_ID].values()) == 1


def test_profile_get_and_patch(context):
    profile = context.client.get("/api/v1/profile")
    assert profile.status_code == 200
    assert profile.json()["data"]["current_soc"] == "72.50"
    response = context.client.patch("/api/v1/profile", json={
        "name": "Updated driver", "battery_kwh": 72, "current_soc": 68.5,
    })
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Updated driver"
    assert response.json()["data"]["id"] == str(USER_ID)
    assert response.json()["data"]["current_soc"] == "68.5"


def test_profile_rejects_invalid_current_charge(context):
    response = context.client.patch("/api/v1/profile", json={"current_soc": 100.1})
    assert response.status_code == 422


def test_profile_rejects_client_identity_field(context):
    response = context.client.patch("/api/v1/profile", json={"id": str(OTHER_USER_ID), "name": "attacker"})
    assert response.status_code == 422


def test_nearby_vendor_details_and_vendor_slots(context):
    nearby = context.client.get("/api/v1/vendors/nearby?lat=18.3&lng=83.9&radius_km=30")
    assert nearby.status_code == 200
    assert nearby.json()["data"][0]["vendor"]["name"] == "Demo Dhaba"
    assert nearby.json()["data"][0]["vendor"]["type"] == "restaurant"
    detail = context.client.get(f"/api/v1/vendors/{VENDOR_ID}")
    assert detail.status_code == 200
    slots = context.client.get(f"/api/v1/vendors/{VENDOR_ID}/slots")
    assert slots.status_code == 200
    assert slots.json()["data"][0]["status"] == "available"


def test_vendor_bookings_scope_comes_from_authenticated_owner(context):
    response = context.client.get(
        f"/api/v1/vendor/bookings?vendor_id={OTHER_USER_ID}&status=confirmed"
    )
    assert response.status_code == 200
    assert context.database.vendor_scope_calls == [("bookings", USER_ID, VENDOR_ID, "confirmed")]


def test_vendor_without_owned_profile_cannot_read_vendor_bookings(context):
    async def other_user():
        return AuthenticatedUser(id=OTHER_USER_ID)

    app.dependency_overrides[get_current_user] = other_user
    response = context.client.get(f"/api/v1/vendor/bookings?vendor_id={VENDOR_ID}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "VENDOR_PROFILE_NOT_FOUND"
    assert context.database.vendor_scope_calls == []


def test_customer_cannot_access_admin_api(context):
    response = context.client.get("/api/v1/admin/me")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_ACCESS_REQUIRED"


def test_vendor_cannot_access_admin_api(context):
    context.database.pool.identity_record = {
        "user_id": OTHER_USER_ID, "role_name": "OPERATIONS_ADMIN", "is_active": True,
        "permissions": ["vendors:read"],
    }
    response = context.client.get("/api/v1/admin/me", headers={"X-Admin-Role": "SUPER_ADMIN"})
    assert response.status_code == 403


def test_support_admin_cannot_issue_refunds(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "SUPPORT_ADMIN", "is_active": True,
        "permissions": ["disputes:read", "disputes:manage", "bookings:read"],
    }
    response = context.client.post(
        "/api/v1/admin/refunds", json={"booking_id": str(uuid4()), "amount_inr": "100", "reason": "Customer resolution"},
        headers={"Idempotency-Key": "refund-test-key-01"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_PERMISSION_REQUIRED"


def test_operations_admin_cannot_issue_refunds(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "OPERATIONS_ADMIN", "is_active": True,
        "permissions": ["bookings:read", "vendors:read", "vendor_onboarding:manage"],
    }
    response = context.client.post(
        "/api/v1/admin/refunds", json={"booking_id": str(uuid4()), "reason": "Refund request review"},
        headers={"Idempotency-Key": "refund-test-key-02"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_PERMISSION_REQUIRED"


def test_support_admin_cannot_approve_refunds(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "SUPPORT_ADMIN", "is_active": True,
        "permissions": ["refunds:read", "refunds:create", "disputes:manage"],
    }
    response = context.client.post(
        f"/api/v1/admin/refunds/{uuid4()}/approve", json={"reason": "Reviewed customer request"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_PERMISSION_REQUIRED"


def test_operations_admin_cannot_approve_refunds(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "OPERATIONS_ADMIN", "is_active": True,
        "permissions": ["bookings:read", "vendors:read", "vendor_onboarding:manage"],
    }
    response = context.client.post(
        f"/api/v1/admin/refunds/{uuid4()}/approve", json={"reason": "Reviewed customer request"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_PERMISSION_REQUIRED"


def test_customer_creates_dispute_from_owned_booking_and_replay_is_idempotent(context):
    booking_id = context.database.dispute_booking["id"]
    headers = {"Idempotency-Key": "customer-dispute-0001"}
    payload = {"booking_id": str(booking_id), "reason": "Charging service issue", "description": "The charger was unavailable after confirmation."}
    first = context.client.post("/api/v1/disputes", json=payload, headers=headers)
    replay = context.client.post("/api/v1/disputes", json=payload, headers=headers)
    assert first.status_code == 201
    assert first.json()["data"]["customer_id"] == str(USER_ID)
    assert first.json()["data"]["vendor_id"] == str(VENDOR_ID)
    assert first.json()["data"]["amount_inr"] == "350.00"
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]
    assert len(context.database.dispute_rows) == 1


def test_customer_cannot_forge_dispute_financial_parties(context):
    response = context.client.post("/api/v1/disputes", json={
        "booking_id": str(context.database.dispute_booking["id"]), "reason": "Charging service issue",
        "description": "The charger was unavailable after confirmation.", "customer_id": str(OTHER_USER_ID),
        "vendor_id": str(OTHER_USER_ID), "amount_inr": "0.01",
    }, headers={"Idempotency-Key": "customer-dispute-0002"})
    assert response.status_code == 422


def test_customer_can_read_own_dispute_but_not_another_customers(context):
    response = context.client.post("/api/v1/disputes", json={
        "booking_id": str(context.database.dispute_booking["id"]), "reason": "Charging service issue",
        "description": "The charger was unavailable after confirmation.",
    }, headers={"Idempotency-Key": "customer-dispute-0003"})
    dispute_id = response.json()["data"]["id"]
    assert context.client.get(f"/api/v1/disputes/{dispute_id}").status_code == 200
    context.database.dispute_rows[UUID(dispute_id)]["customer_id"] = OTHER_USER_ID
    assert context.client.get(f"/api/v1/disputes/{dispute_id}").status_code == 404


def test_vendor_sees_only_own_disputes_and_cannot_approve_refund(context):
    owned = {"id": uuid4(), "booking_id": uuid4(), "customer_id": USER_ID, "vendor_id": VENDOR_ID,
             "amount_inr": Decimal("350"), "reason": "Issue", "description": "Details", "status": "open", "timeline": []}
    unrelated = {**owned, "id": uuid4(), "vendor_id": uuid4()}
    context.database.dispute_rows.update({owned["id"]: owned, unrelated["id"]: unrelated})
    listed = context.client.get("/api/v1/vendor/disputes")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]["items"]] == [str(owned["id"])]
    assert context.client.get(f"/api/v1/vendor/disputes/{unrelated['id']}").status_code == 404
    denied = context.client.post(f"/api/v1/admin/refunds/{uuid4()}/approve", json={"reason": "Vendor cannot approve"})
    assert denied.status_code == 403


def test_customer_dispute_rejects_unpaid_booking(context):
    context.database.dispute_booking["payment_status"] = "pending"
    response = context.client.post("/api/v1/disputes", json={
        "booking_id": str(context.database.dispute_booking["id"]), "reason": "Charging service issue",
        "description": "The charger was unavailable after confirmation.",
    }, headers={"Idempotency-Key": "customer-dispute-0004"})
    assert response.status_code == 409


def test_vendor_can_respond_but_cannot_change_dispute_state(context):
    row = {"id": uuid4(), "booking_id": uuid4(), "customer_id": USER_ID, "vendor_id": VENDOR_ID,
           "amount_inr": Decimal("350"), "reason": "Issue", "description": "Details", "status": "open", "timeline": []}
    context.database.dispute_rows[row["id"]] = row
    response = context.client.post(f"/api/v1/vendor/disputes/{row['id']}/messages", json={"message": "We are checking the charger."},
                                   headers={"Idempotency-Key": "vendor-message-0001"})
    assert response.status_code == 200
    assert row["status"] == "open"
    assert row["timeline"][0]["actor_type"] == "vendor"


def test_support_admin_can_manage_dispute_and_finance_can_reach_refund_action(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "SUPPORT_ADMIN", "is_active": True,
        "permissions": ["disputes:read", "disputes:manage"],
    }

    async def fake_action(self, actor_id, role, dispute_id, action, message, metadata, idempotency_key):
        return {"id": dispute_id, "status": "resolved", "action": action}

    with patch.object(AdminRepository, "dispute_action", fake_action):
        response = context.client.post(f"/api/v1/admin/disputes/{uuid4()}/action",
            json={"action": "resolve", "message": "Customer evidence reviewed"},
            headers={"Idempotency-Key": "admin-dispute-action-1"})
    assert response.status_code == 200
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "FINANCE_ADMIN", "is_active": True,
        "permissions": ["refunds:approve", "refunds:create", "refunds:read"],
    }
    finance_response = context.client.post(f"/api/v1/admin/refunds/{uuid4()}/approve", json={"reason": "Finance approval review"})
    assert finance_response.status_code == 404


def test_partial_refund_server_amount_validation():
    amount, balance = validate_refund_amount(Decimal("500.00"), Decimal("125.00"), Decimal("200.00"))
    assert amount == Decimal("200.00")
    assert balance == Decimal("175.00")
    with pytest.raises(ApiError) as error:
        validate_refund_amount(Decimal("500.00"), Decimal("450.00"), Decimal("51.00"))
    assert error.value.status_code == 409


def test_duplicate_refund_request_is_idempotent_and_second_active_refund_is_rejected():
    pool = FakeRefundPool()
    repository = AdminRepository(pool)
    async def submit(key):
        return await repository.create_refund_request(
            USER_ID, pool.connection.booking_id, Decimal("100.00"), "Approved customer adjustment",
            key, "FINANCE_ADMIN", {"request_id": "test"},
        )
    first, created = asyncio.run(submit("refund-request-key-0001"))
    replay, replay_created = asyncio.run(submit("refund-request-key-0001"))
    assert created is True and replay_created is False
    assert first["id"] == replay["id"]
    assert len(pool.connection.refunds) == 1
    assert pool.connection.audit_count == 1
    with pytest.raises(ApiError) as error:
        asyncio.run(submit("refund-request-key-0002"))
    assert error.value.status_code == 409


def test_financial_consistency_diagnostics_report_impossible_states():
    findings = check_financial_consistency({
        "booking_id": "booking-1", "booking_status": "confirmed", "booking_amount": "500",
        "payment_status": "captured", "payment_amount": "500", "webhook_verified": True,
        "reserved_refund_amount": "501",
    })
    assert [item["code"] for item in findings] == ["REFUNDS_EXCEED_PAYMENT"]
    refunded = check_financial_consistency({"booking_id": "booking-2", "payment_status": "refunded",
        "payment_amount": "500", "reserved_refund_amount": "250", "completed_refund_amount": "250"})
    assert [item["code"] for item in refunded] == ["REFUNDED_PAYMENT_TOTAL_MISMATCH"]


def test_dispute_and_admin_audit_immutability_are_enforced_by_new_migration():
    migration = Path(__file__).parents[3] / "supabase" / "migrations" / "202610020005_dispute_hardening.sql"
    sql = migration.read_text(encoding="utf-8")
    assert "dispute_events_immutable" in sql
    assert "Dispute events are immutable" in sql
    admin_migration = migration.with_name("202610020004_admin_platform.sql").read_text(encoding="utf-8")
    assert "admin_audit_immutable" in admin_migration
    assert "Admin audit records are immutable" in admin_migration


def test_customer_cannot_forge_dispute_financial_parties(context):
    response = context.client.post("/api/v1/disputes", json={
        "booking_id": str(context.database.dispute_booking["id"]), "reason": "Charging service issue",
        "description": "The charger was unavailable after confirmation.", "customer_id": str(OTHER_USER_ID),
        "vendor_id": str(OTHER_USER_ID), "amount_inr": "0.01",
    }, headers={"Idempotency-Key": "customer-dispute-0002"})
    assert response.status_code == 422


def test_customer_can_read_own_dispute_but_not_another_customers(context):
    response = context.client.post("/api/v1/disputes", json={
        "booking_id": str(context.database.dispute_booking["id"]), "reason": "Charging service issue",
        "description": "The charger was unavailable after confirmation.",
    }, headers={"Idempotency-Key": "customer-dispute-0003"})
    dispute_id = response.json()["data"]["id"]
    assert context.client.get(f"/api/v1/disputes/{dispute_id}").status_code == 200
    context.database.dispute_rows[UUID(dispute_id)]["customer_id"] = OTHER_USER_ID
    assert context.client.get(f"/api/v1/disputes/{dispute_id}").status_code == 404


def test_vendor_sees_only_own_disputes_and_cannot_approve_refund(context):
    owned = {"id": uuid4(), "booking_id": uuid4(), "customer_id": USER_ID, "vendor_id": VENDOR_ID,
             "amount_inr": Decimal("350"), "reason": "Issue", "description": "Details", "status": "open", "timeline": []}
    unrelated = {**owned, "id": uuid4(), "vendor_id": uuid4()}
    context.database.dispute_rows.update({owned["id"]: owned, unrelated["id"]: unrelated})
    listed = context.client.get("/api/v1/vendor/disputes")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]["items"]] == [str(owned["id"])]
    assert context.client.get(f"/api/v1/vendor/disputes/{unrelated['id']}").status_code == 404
    denied = context.client.post(f"/api/v1/admin/refunds/{uuid4()}/approve", json={"reason": "Vendor cannot approve"})
    assert denied.status_code == 403


def test_customer_dispute_rejects_unpaid_booking(context):
    context.database.dispute_booking["payment_status"] = "pending"
    response = context.client.post("/api/v1/disputes", json={
        "booking_id": str(context.database.dispute_booking["id"]), "reason": "Charging service issue",
        "description": "The charger was unavailable after confirmation.",
    }, headers={"Idempotency-Key": "customer-dispute-0004"})
    assert response.status_code == 409


def test_vendor_manager_approval_updates_platform_state_and_audit(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "VENDOR_MANAGER", "is_active": True,
        "permissions": ["vendors:read", "vendors:manage", "vendor_onboarding:manage"],
    }
    response = context.client.post(f"/api/v1/admin/vendor-onboarding/{VENDOR_ID}/action", json={
        "action": "approve", "reason": "Business details and location verified",
    })
    assert response.status_code == 200
    assert context.database.pool.vendor_state["status"] == "approved"
    assert context.database.pool.vendor_state["is_active"] is True
    assert context.database.pool.vendor_state["is_verified"] is True
    assert context.database.pool.audit_rows == 1


def test_operations_admin_can_suspend_and_audit_vendor(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "OPERATIONS_ADMIN", "is_active": True,
        "permissions": ["vendors:read", "vendors:manage"],
    }
    context.database.pool.vendor_state.update({"status": "approved", "is_active": True, "is_verified": True})
    response = context.client.post(f"/api/v1/admin/vendors/{VENDOR_ID}/action", json={
        "action": "suspend", "reason": "Repeated operating standard violations",
    })
    assert response.status_code == 200
    assert context.database.pool.vendor_state["status"] == "suspended"
    assert context.database.pool.vendor_state["is_active"] is False
    assert context.database.pool.audit_rows == 1


def test_support_admin_cannot_read_finance_transactions(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "SUPPORT_ADMIN", "is_active": True,
        "permissions": ["bookings:read", "disputes:read", "disputes:manage"],
    }
    response = context.client.get("/api/v1/admin/transactions")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_PERMISSION_REQUIRED"


def test_finance_admin_can_read_transactions(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "FINANCE_ADMIN", "is_active": True,
        "permissions": ["transactions:read"],
    }
    expected = {"items": [], "total": 0, "limit": 50, "offset": 0, "fee_disclosure": "unavailable"}
    with patch("app.admin.router.AdminRepository.transactions", new=AsyncMock(return_value=expected)):
        response = context.client.get("/api/v1/admin/transactions")
    assert response.status_code == 200
    assert response.json()["data"] == expected


def test_finance_admin_cannot_access_disputes(context):
    context.database.pool.identity_record = {
        "user_id": USER_ID, "role_name": "FINANCE_ADMIN", "is_active": True,
        "permissions": ["transactions:read", "refunds:read", "refunds:create"],
    }
    response = context.client.get("/api/v1/admin/disputes")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_PERMISSION_REQUIRED"


def test_invalid_nearby_coordinates_are_422(context):
    response = context.client.get("/api/v1/vendors/nearby?lat=181&lng=0&radius_km=10")
    assert response.status_code == 422


def test_get_slot(context):
    response = context.client.get(f"/api/v1/slots/{SLOT_ID}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(SLOT_ID)


def test_list_bookings_is_scoped_to_authenticated_user(context):
    response = context.client.get("/api/v1/bookings")
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_invalid_slot_cannot_be_locked(context):
    response = context.client.post("/api/v1/bookings/lock", json={"slot_id": str(uuid4())})
    assert response.status_code == 404


def test_booking_creation_is_pending_until_webhook(context):
    lock = context.client.post("/api/v1/bookings/lock", json={"slot_id": str(SLOT_ID)})
    assert lock.status_code == 200
    token = lock.json()["data"]["lock_token"]
    response = context.client.post("/api/v1/bookings", json={"slot_id": str(SLOT_ID), "lock_token": token})
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    assert response.json()["data"]["amount_paid"] == "0.00"
    assert response.json()["data"]["payment"]["status"] == "pending"


def test_lock_cannot_be_reused_or_used_by_other_user(context):
    lock = context.client.post("/api/v1/bookings/lock", json={"slot_id": str(SLOT_ID)})
    token = lock.json()["data"]["lock_token"]
    context.redis.values[f"voltstop:booking-lock:{SLOT_ID}"] = f"{OTHER_USER_ID}:{token}"
    response = context.client.post("/api/v1/bookings", json={"slot_id": str(SLOT_ID), "lock_token": token})
    assert response.status_code == 409


def test_booking_conflict_when_slot_was_already_booked(context):
    lock = context.client.post("/api/v1/bookings/lock", json={"slot_id": str(SLOT_ID)})
    context.database.force_booking_conflict = True
    response = context.client.post("/api/v1/bookings", json={
        "slot_id": str(SLOT_ID), "lock_token": lock.json()["data"]["lock_token"]
    })
    assert response.status_code == 409


def test_user_cannot_read_someone_elses_booking(context):
    lock = context.client.post("/api/v1/bookings/lock", json={"slot_id": str(SLOT_ID)})
    created = context.client.post("/api/v1/bookings", json={
        "slot_id": str(SLOT_ID), "lock_token": lock.json()["data"]["lock_token"]
    })
    booking_id = created.json()["data"]["id"]

    async def other_user():
        return AuthenticatedUser(id=OTHER_USER_ID)

    app.dependency_overrides[get_current_user] = other_user
    response = context.client.get(f"/api/v1/bookings/{booking_id}")
    assert response.status_code == 403


def test_booking_cancel(context):
    lock = context.client.post("/api/v1/bookings/lock", json={"slot_id": str(SLOT_ID)})
    created = context.client.post("/api/v1/bookings", json={
        "slot_id": str(SLOT_ID), "lock_token": lock.json()["data"]["lock_token"]
    })
    booking_id = created.json()["data"]["id"]
    response = context.client.post(f"/api/v1/bookings/{booking_id}/cancel")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "cancelled"


def test_razorpay_webhook_signature():
    body = b'{"event":"payment.captured"}'
    import hashlib
    import hmac
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, signature, "secret")
    assert not verify_webhook_signature(body, "bad-signature", "secret")


def test_signed_payment_webhook_confirms_once_and_replay_has_no_duplicate_effect(context):
    import hashlib
    import hmac

    lock = context.client.post("/api/v1/bookings/lock", json={"slot_id": str(SLOT_ID)})
    created = context.client.post("/api/v1/bookings", json={
        "slot_id": str(SLOT_ID), "lock_token": lock.json()["data"]["lock_token"]
    })
    order_id = created.json()["data"]["payment"]["order_id"]
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_test_capture", "order_id": order_id, "amount": 35000, "currency": "INR",
    }}}}).encode()
    old_secret = get_settings().razorpay_webhook_secret
    get_settings().razorpay_webhook_secret = "payment-test-secret"
    signature = hmac.new(b"payment-test-secret", body, hashlib.sha256).hexdigest()
    headers = {"X-Razorpay-Signature": signature, "Content-Type": "application/json"}
    try:
        first = context.client.post("/api/v1/payments/razorpay/webhook", content=body, headers=headers)
        after_first = (
            context.database.booking_record["status"],
            context.database.booking_record["payment_status"],
            context.database.booking_record["amount_paid"],
            list(context.database.payment_webhook_events),
        )
        second = context.client.post("/api/v1/payments/razorpay/webhook", content=body, headers=headers)
    finally:
        get_settings().razorpay_webhook_secret = old_secret

    assert first.status_code == second.status_code == 200
    assert after_first == (
        "confirmed", "captured", Decimal("350.00"), ["payment_success", "confirmed"]
    )
    assert context.database.booking_record["status"] == "confirmed"
    assert context.database.booking_record["payment_status"] == "captured"
    assert context.database.booking_record["amount_paid"] == Decimal("350.00")
    assert context.database.payment_webhook_events == ["payment_success", "confirmed"]


def test_valid_signature_with_wrong_payment_id_does_not_change_financial_state(context):
    import hashlib
    import hmac

    lock = context.client.post("/api/v1/bookings/lock", json={"slot_id": str(SLOT_ID)})
    created = context.client.post("/api/v1/bookings", json={
        "slot_id": str(SLOT_ID), "lock_token": lock.json()["data"]["lock_token"]
    })
    order_id = created.json()["data"]["payment"]["order_id"]
    booking = context.database.booking_record
    booking.update(status="confirmed", payment_status="captured", amount_paid=Decimal("350.00"),
                   razorpay_payment_id="pay_test_correct")
    before = (dict(booking), list(context.database.payment_webhook_events))
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_test_wrong", "order_id": order_id, "amount": 35000, "currency": "INR",
    }}}}).encode()
    old_secret = get_settings().razorpay_webhook_secret
    get_settings().razorpay_webhook_secret = "payment-test-secret"
    signature = hmac.new(b"payment-test-secret", body, hashlib.sha256).hexdigest()
    try:
        response = context.client.post("/api/v1/payments/razorpay/webhook", content=body,
            headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"})
    finally:
        get_settings().razorpay_webhook_secret = old_secret

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PAYMENT_WEBHOOK_REJECTED"
    assert response.json()["error"]["message"] == "Webhook payment could not be verified"
    assert (context.database.booking_record, context.database.payment_webhook_events) == before


def test_signed_razorpay_refund_webhook_updates_backend(context):
    import hashlib
    import hmac
    old_secret = get_settings().razorpay_webhook_secret
    get_settings().razorpay_webhook_secret = "refund-test-secret"
    body = json.dumps({"event": "refund.processed", "payload": {"refund": {"entity": {
        "id": "rfnd_test_123", "payment_id": "pay_test_456", "amount": 12500, "status": "processed",
        "currency": "INR",
        "notes": {"voltstop_refund_id": "refund-row-123"},
    }}}}).encode()
    signature = hmac.new(b"refund-test-secret", body, hashlib.sha256).hexdigest()
    try:
        response = context.client.post("/api/v1/payments/razorpay/webhook", content=body,
                                       headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"})
    finally:
        get_settings().razorpay_webhook_secret = old_secret
    assert response.status_code == 200
    assert context.database.refund_webhook == ("rfnd_test_123", "pay_test_456", 12500, "INR", "processed", "refund-row-123")


class FakeRouteProvider:
    async def route(self, origin, destination):
        return RouteResult(100_000, '{"type":"LineString","coordinates":[[80,16],[84,18]]}', "test_provider", 5400)


def test_pilot_route_service_uses_provider_distance():
    class FakeRouteDatabase:
        async def recommended_route_vendors(self, geojson):
            assert "LineString" in geojson
            return [{"vendor": {"name": "Demo Dhaba"}}]

    async def run():
        result = await PilotRouteService(FakeRouteProvider()).plan(
            "Srikakulam", "Vijayawada", 60, 80, 6, FakeRouteDatabase()
        )
        assert result["distance_km"] == 100
        assert result["distance_source"] == "test_provider"
        assert result["estimated_consumption_kwh"] == round(100 / 6, 2)
        assert result["route_coordinates"] == [[80, 16], [84, 18]]
        assert result["estimated_duration_seconds"] == 5400

    import asyncio
    asyncio.run(run())


def test_route_plan_requires_authentication(context):
    override = app.dependency_overrides.pop(get_current_user)
    try:
        response = context.client.post("/api/v1/routes/plan", json={
            "origin": "Srikakulam", "destination": "Vijayawada",
            "battery_kwh": 60, "current_soc": 75,
            "efficiency_km_per_kwh": 6, "persist": False,
        })
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = override


def test_route_plan_persists_under_authenticated_driver(context):
    app.dependency_overrides[route_service] = lambda: PilotRouteService(FakeRouteProvider())
    response = context.client.post("/api/v1/routes/plan", json={
        "origin": "Srikakulam", "destination": "Vijayawada",
        "battery_kwh": 60, "current_soc": 75,
        "efficiency_km_per_kwh": 6, "persist": True,
    })

    assert response.status_code == 200
    assert response.json()["data"]["route_id"]
    assert len(context.database.saved_routes) == 1
    user_id, request, _, _ = context.database.saved_routes[0]
    assert user_id == USER_ID
    assert request.current_soc == 75


def test_route_departure_time_is_timezone_aware_and_persisted(context):
    app.dependency_overrides[route_service] = lambda: PilotRouteService(FakeRouteProvider())
    departure = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    response = context.client.post("/api/v1/routes/plan", json={
        "origin": "Srikakulam", "destination": "Vijayawada",
        "battery_kwh": 60, "current_soc": 75,
        "efficiency_km_per_kwh": 6, "persist": True,
        "departure_at": departure,
    })
    assert response.status_code == 200
    assert response.json()["data"]["departure_at"].endswith("+00:00")
    assert context.database.saved_routes[-1][1].departure_at is not None

    naive = context.client.post("/api/v1/routes/plan", json={
        "origin": "Srikakulam", "destination": "Vijayawada",
        "battery_kwh": 60, "current_soc": 75,
        "efficiency_km_per_kwh": 6, "persist": False,
        "departure_at": "2020-01-01T12:00:00",
    })
    assert naive.status_code == 422


def test_vehicle_routes_require_authentication(context):
    override = app.dependency_overrides.pop(get_current_user)
    try:
        assert context.client.get("/api/v1/vehicles").status_code == 401
    finally:
        app.dependency_overrides[get_current_user] = override


def test_route_service_rejects_non_pilot_route():
    async def run():
        with pytest.raises(ApiError) as error:
            await PilotRouteService(FakeRouteProvider()).plan(
                "Chennai", "Vijayawada", 60, 80, 6, FakeDatabase()
            )
        assert error.value.status_code == 422

    import asyncio
    asyncio.run(run())
