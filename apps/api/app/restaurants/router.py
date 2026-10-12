from typing import Any, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.admin.auth import AdminContext, require_permission
from app.auth.dependencies import CurrentUser
from app.core.config import Settings, get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.errors import ApiError
from app.core.responses import success
from app.payments.service import RazorpayGateway
from app.restaurants.repository import RestaurantRepository
from app.restaurants.schemas import CategoryCreate, MenuItemCreate, MenuItemPatch, OrderCreate, OrderStatusUpdate
from app.vendors.portal_router import _vendor_id

router = APIRouter(prefix="/restaurants", tags=["restaurant-orders"])
vendor_router = APIRouter(prefix="/vendor/restaurants", tags=["vendor-restaurants"])
admin_router = APIRouter(prefix="/admin/restaurant-orders", tags=["admin-restaurant-orders"])


def _repo(database):
    return RestaurantRepository(database.pool)


@router.get("/{vendor_id}/menu")
async def get_menu(vendor_id: UUID, _user: CurrentUser, database: DatabaseDependency):
    menu = await _repo(database).menu(vendor_id)
    if menu is None:
        raise ApiError(404, "RESTAURANT_NOT_FOUND", "Restaurant menu was not found")
    return success(menu)


@router.post("/orders", status_code=201)
async def create_order(payload: OrderCreate, request: Request, user: CurrentUser, database: DatabaseDependency,
                       settings: Settings = Depends(get_settings),
                       idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128)) -> dict[str, Any]:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise ApiError(503, "PAYMENT_UNAVAILABLE", "Razorpay is not configured; order checkout is unavailable")
    repo = _repo(database)
    order, created = await repo.create_order(user.id, payload.model_dump(), idempotency_key)
    payment = await repo.payment_for_order(order["id"])
    if payment is None:
        raise ApiError(500, "PAYMENT_RECORD_MISSING", "Order payment could not be initialized")
    if payment["razorpay_order_id"]:
        provider_order = {"order_id": payment["razorpay_order_id"], "amount_paise": int(payment["amount_inr"] * 100), "currency": payment["currency"], "key_id": settings.razorpay_key_id}
    elif created and payment["order_state"] == "creating":
        try:
            provider_order = await RazorpayGateway(request.app.state.http_client, settings).create_order(order["id"], payment["amount_inr"])
            await repo.attach_order(order["id"], provider_order["order_id"])
        except Exception:
            await repo.mark_order_unknown(order["id"])
            raise
    else:
        raise ApiError(503, "PAYMENT_RECONCILIATION_REQUIRED", "Payment order state is being reconciled; do not retry payment")
    order["payment"] = {**provider_order, "status": payment["status"], "webhook_verified": payment["webhook_verified"]}
    return success(order, "Order created; payment confirmation is pending")


@router.get("/orders")
async def my_orders(user: CurrentUser, database: DatabaseDependency):
    return success(await _repo(database).orders(user.id))



@vendor_router.get("/menu")
async def vendor_menu(user: CurrentUser, database: DatabaseDependency):
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).vendor_menu(user.id, vendor_id))


@vendor_router.post("/categories", status_code=201)
async def create_category(payload: CategoryCreate, user: CurrentUser, database: DatabaseDependency):
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).create_category(user.id, vendor_id, payload.name, payload.sort_order), "Category created")


@vendor_router.post("/items", status_code=201)
async def create_menu_item(payload: MenuItemCreate, user: CurrentUser, database: DatabaseDependency):
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).upsert_item(user.id, vendor_id, payload.model_dump()), "Menu item created")


@vendor_router.patch("/items/{item_id}")
async def update_menu_item(item_id: UUID, payload: MenuItemPatch, user: CurrentUser, database: DatabaseDependency):
    vendor_id = await _vendor_id(user, database)
    current = await _repo(database).vendor_menu(user.id, vendor_id)
    match = next(((category, item) for category in current["categories"] for item in category["items"] if str(item["id"]) == str(item_id)), None)
    if match is None:
        raise ApiError(404, "MENU_ITEM_NOT_FOUND", "Menu item was not found")
    category, existing = match
    updates = {"category_id": category["id"], "name": existing["name"], "description": existing["description"],
               "price_inr": existing["price_inr"], "is_available": existing["is_available"], "options": existing["options"]}
    updates.update(payload.model_dump(exclude_unset=True))
    validated = MenuItemCreate.model_validate(updates).model_dump()
    return success(await _repo(database).upsert_item(user.id, vendor_id, validated, item_id), "Menu item updated")


@vendor_router.get("/orders")
async def vendor_orders(user: CurrentUser, database: DatabaseDependency):
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).vendor_orders(user.id, vendor_id))


@vendor_router.get("/financials")
async def vendor_restaurant_financials(user: CurrentUser, database: DatabaseDependency):
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).vendor_sales(user.id, vendor_id))


@vendor_router.post("/orders/{order_id}/status")
async def update_order_status(order_id: UUID, payload: OrderStatusUpdate, user: CurrentUser,
                              database: DatabaseDependency):
    vendor_id = await _vendor_id(user, database)
    return success(await _repo(database).transition(user.id, vendor_id, order_id, payload.status), "Order status updated")


@admin_router.get("")
async def admin_orders(admin: Annotated[AdminContext, Depends(require_permission("bookings:read"))],
                       database: DatabaseDependency, vendor_id: UUID | None = None):
    return success(await _repo(database).vendor_orders(admin.user_id, vendor_id, admin=True))
