from datetime import datetime
from decimal import Decimal
from typing import Any, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from redis.exceptions import RedisError

from app.admin.auth import AdminContext, require_admin, require_permission
from app.admin.refund_service import RefundService
from app.admin.repository import AdminRepository
from app.admin.schemas import AdminUserPatch, DisputeAction, DisputeCreate, DisputeRefundCreate, RefundCreate, RefundDecision, VendorAction
from app.core.config import Settings, get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.dependencies import get_http_client, get_redis
from app.core.errors import ApiError
from app.core.responses import success
from app.hotels.repository import HotelRepository
from app.hotels.refunds import HotelRefundService

router = APIRouter(prefix="/admin", tags=["admin-platform"])


def _metadata(request: Request) -> dict[str, Any]:
    return {"ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent", "")[:500],
            "request_id": request.headers.get("x-request-id", "")[:120]}


@router.get("/me")
async def admin_me(admin: Annotated[AdminContext, Depends(require_admin)]) -> dict[str, Any]:
    return success({"user_id": str(admin.user_id), "email": admin.email,
                    "role": admin.role_name, "permissions": sorted(admin.permissions)})


@router.get("/dashboard")
async def dashboard(_admin: Annotated[AdminContext, Depends(require_permission("dashboard:read"))],
                    database: DatabaseDependency) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).dashboard())


@router.get("/analytics")
async def analytics(_admin: Annotated[AdminContext, Depends(require_permission("analytics:read"))],
                    database: DatabaseDependency) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).dashboard())


@router.get("/vendors")
async def vendors(
    admin: Annotated[AdminContext, Depends(require_permission("vendors:read"))], database: DatabaseDependency,
    search: str | None = Query(default=None, max_length=160),
    status: str | None = Query(default=None, pattern="^(pending|under_review|changes_requested|approved|rejected|suspended)$"),
    vendor_type: str | None = Query(default=None, alias="type", pattern="^(restaurant|hotel)$"),
    location: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    data = await AdminRepository(database.pool).vendors(search, status, vendor_type, location, limit, offset,
                                                        include_financials="vendor_financials:read" in admin.permissions)
    return success(data)


@router.get("/vendors/{vendor_id}")
async def vendor_detail(vendor_id: UUID,
    _admin: Annotated[AdminContext, Depends(require_permission("vendors:read"))], database: DatabaseDependency
) -> dict[str, Any]:
    data = await AdminRepository(database.pool).vendor(vendor_id)
    if data is None:
        raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor was not found")
    return success(data)


@router.get("/vendors/{vendor_id}/financials")
async def vendor_financials(vendor_id: UUID,
    _admin: Annotated[AdminContext, Depends(require_permission("vendor_financials:read"))], database: DatabaseDependency
) -> dict[str, Any]:
    data = await AdminRepository(database.pool).vendor_financials(vendor_id)
    if data is None:
        raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor was not found")
    return success(data)


@router.get("/vendors/{vendor_id}/availability")
async def vendor_availability(vendor_id: UUID,
    _admin: Annotated[AdminContext, Depends(require_permission("vendors:read"))], database: DatabaseDependency
) -> dict[str, Any]:
    repository = AdminRepository(database.pool)
    if await repository.vendor(vendor_id) is None:
        raise ApiError(404, "VENDOR_NOT_FOUND", "Vendor was not found")
    return success(await repository.vendor_availability(vendor_id))


@router.post("/vendors/{vendor_id}/action")
async def vendor_action(vendor_id: UUID, payload: VendorAction, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("vendors:manage"))], database: DatabaseDependency
) -> dict[str, Any]:
    if payload.action in ("approve", "request_changes", "reject", "review") and "vendor_onboarding:manage" not in admin.permissions:
        raise ApiError(403, "ADMIN_PERMISSION_REQUIRED", "Your role cannot review vendor onboarding")
    repository = AdminRepository(database.pool)
    result = await repository.vendor_action(admin.user_id, admin.role_name, vendor_id, payload.action, payload.reason, _metadata(request))
    return success(result, f"Vendor {payload.action.replace('_', ' ')} completed")


@router.get("/vendor-onboarding")
async def onboarding(_admin: Annotated[AdminContext, Depends(require_permission("vendor_onboarding:manage"))],
                     database: DatabaseDependency,
                     status: str | None = Query(default=None, pattern="^(pending|under_review|changes_requested|approved|rejected|suspended)$"),
                     limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    data = await AdminRepository(database.pool).vendors(None, status, None, None, limit, offset)
    return success(data)


@router.post("/vendor-onboarding/{vendor_id}/action")
async def onboarding_action(vendor_id: UUID, payload: VendorAction, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("vendor_onboarding:manage"))], database: DatabaseDependency
) -> dict[str, Any]:
    result = await AdminRepository(database.pool).vendor_action(admin.user_id, admin.role_name, vendor_id, payload.action,
                                                                 payload.reason, _metadata(request))
    return success(result, f"Vendor application {payload.action.replace('_', ' ')}")


@router.get("/bookings")
async def bookings(
    _admin: Annotated[AdminContext, Depends(require_permission("bookings:read"))], database: DatabaseDependency,
    search: str | None = Query(default=None, max_length=160),
    status: str | None = Query(default=None, pattern="^(pending|confirmed|cancelled|completed|expired)$"),
    payment_status: str | None = Query(default=None, pattern="^(pending|authorized|captured|failed|refunded)$"),
    service: str | None = Query(default=None, max_length=80), vendor_id: UUID | None = None,
    start: datetime | None = None, end: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    if start and start.utcoffset() is None or end and end.utcoffset() is None:
        raise ApiError(422, "TIMEZONE_REQUIRED", "Date filters must include a timezone")
    data = await AdminRepository(database.pool).bookings(search, status, payment_status, service, vendor_id,
                                                         start, end, limit, offset)
    return success(data)


@router.get("/bookings/{booking_id}")
async def booking_detail(booking_id: UUID,
    _admin: Annotated[AdminContext, Depends(require_permission("bookings:read"))], database: DatabaseDependency
) -> dict[str, Any]:
    data = await AdminRepository(database.pool).booking(booking_id)
    if data is None:
        raise ApiError(404, "BOOKING_NOT_FOUND", "Booking was not found")
    return success(data)


@router.get("/live-operations")
async def live_operations(_admin: Annotated[AdminContext, Depends(require_permission("operations:read"))],
                          database: DatabaseDependency, redis=Depends(get_redis),
                          settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    repository = AdminRepository(database.pool)
    vendors = await repository.live_operations()
    slots = await repository.live_operation_slots()
    try:
        values = await redis.mget(*[f"{settings.booking_lock_prefix}{slot['id']}" for slot in slots]) if slots else []
    except RedisError as exc:
        raise ApiError(503, "LOCK_SERVICE_UNAVAILABLE", "Live capacity could not be refreshed") from exc
    by_vendor: dict[UUID, int] = {}
    for slot, lock_value in zip(slots, values):
        if lock_value:
            by_vendor[slot["vendor_id"]] = by_vendor.get(slot["vendor_id"], 0) + 1
    for vendor in vendors:
        held = by_vendor.get(vendor["vendor_id"], 0)
        vendor["held_locks"] = held
        vendor["capacity"] = max(0, int(vendor["capacity"]) - held)
    return success(vendors)


@router.get("/transactions")
async def transactions(
    _admin: Annotated[AdminContext, Depends(require_permission("transactions:read"))], database: DatabaseDependency,
    search: str | None = Query(default=None, max_length=160), status: str | None = None,
    vendor_id: UUID | None = None, start: datetime | None = None, end: datetime | None = None,
    minimum: Decimal | None = Query(default=None, ge=0), maximum: Decimal | None = Query(default=None, ge=0),
    provider: str | None = Query(default=None, pattern="^Razorpay$"),
    limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    if start and start.utcoffset() is None or end and end.utcoffset() is None:
        raise ApiError(422, "TIMEZONE_REQUIRED", "Date filters must include a timezone")
    if minimum is not None and maximum is not None and maximum < minimum:
        raise ApiError(422, "INVALID_AMOUNT_RANGE", "Maximum amount must be greater than or equal to minimum amount")
    return success(await AdminRepository(database.pool).transactions(search, status, vendor_id, start, end,
                                                                     minimum, maximum, provider, limit, offset))


@router.get("/payouts")
async def payouts(_admin: Annotated[AdminContext, Depends(require_permission("payouts:read"))],
                  database: DatabaseDependency, limit: int = Query(default=50, ge=1, le=100),
                  offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).payouts(limit, offset))


@router.get("/refunds")
async def refunds(_admin: Annotated[AdminContext, Depends(require_permission("refunds:read"))],
                  database: DatabaseDependency, status: str | None = Query(default=None, pattern="^(requested|approved|processing|completed|failed|rejected)$"),
                  booking_id: UUID | None = None, limit: int = Query(default=50, ge=1, le=100),
                  offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).refunds(status, booking_id, limit, offset))


@router.get("/refunds/eligibility")
async def refund_eligibility(booking_id: UUID,
    _admin: Annotated[AdminContext, Depends(require_permission("refunds:create"))], database: DatabaseDependency
) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).refund_eligibility(booking_id))


@router.post("/refunds", status_code=202)
async def create_refund(payload: RefundCreate, request: Request, response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    admin: Annotated[AdminContext, Depends(require_permission("refunds:create"))],
    database: DatabaseDependency,
) -> dict[str, Any]:
    data, created = await AdminRepository(database.pool).create_refund_request(
        admin.user_id, payload.booking_id, payload.amount_inr, payload.reason, idempotency_key,
        admin.role_name, _metadata(request),
    )
    response.status_code = 202 if created else 200
    return success(data, "Refund request recorded" if created else "Existing refund request returned")


@router.post("/refunds/{refund_id}/approve", status_code=202)
async def approve_refund(refund_id: UUID, payload: RefundDecision, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("refunds:approve"))],
    database: DatabaseDependency, settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    repository = AdminRepository(database.pool)
    approved = await repository.approve_refund_request(
        admin.user_id, admin.role_name, refund_id, payload.reason, _metadata(request),
    )
    client = await get_http_client(request)
    data, submitted = await RefundService(repository, client, settings).issue(
        admin.user_id, refund_id, payload.reason, admin.role_name, _metadata(request),
    )
    return success(data, "Refund submitted to Razorpay" if submitted else "Refund state returned; provider reconciliation may be pending")


@router.post("/refunds/{refund_id}/reject")
async def reject_refund(refund_id: UUID, payload: RefundDecision, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("refunds:approve"))],
    database: DatabaseDependency,
) -> dict[str, Any]:
    data = await AdminRepository(database.pool).reject_refund_request(
        admin.user_id, admin.role_name, refund_id, payload.reason, _metadata(request),
    )
    return success(data, "Refund request rejected")


@router.get("/hotel-refunds")
async def hotel_refunds(_admin: Annotated[AdminContext, Depends(require_permission("refunds:read"))],
                        database: DatabaseDependency,
                        status: str | None = Query(default=None, pattern="^(requested|approved|processing|completed|failed|rejected)$"),
                        limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return success(await HotelRepository(database.pool).admin_refunds(status,limit,offset))


@router.post("/hotel-refunds/{refund_id}/approve", status_code=202)
async def approve_hotel_refund(refund_id: UUID, payload: RefundDecision, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("refunds:approve"))],
    database: DatabaseDependency, settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    repo=HotelRepository(database.pool)
    approved=await repo.approve_refund(admin.user_id,refund_id,payload.reason)
    await AdminRepository(database.pool).log_action(admin.user_id,admin.role_name,"hotel_refund.approved","hotel_refund",
        str(refund_id),payload.reason,None,{"status":"approved"},_metadata(request))
    client=await get_http_client(request)
    data,submitted=await HotelRefundService(repo,client,settings).issue(refund_id)
    return success(data,"Hotel refund submitted to Razorpay" if submitted else "Hotel refund state returned; provider reconciliation may be pending")


@router.post("/hotel-refunds/{refund_id}/reject")
async def reject_hotel_refund(refund_id: UUID, payload: RefundDecision, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("refunds:approve"))],
    database: DatabaseDependency,
) -> dict[str, Any]:
    data=await HotelRepository(database.pool).reject_refund(admin.user_id,refund_id,payload.reason)
    await AdminRepository(database.pool).log_action(admin.user_id,admin.role_name,"hotel_refund.rejected","hotel_refund",
        str(refund_id),payload.reason,None,{"status":"rejected"},_metadata(request))
    return success(data,"Hotel refund request rejected")


@router.get("/disputes")
async def disputes(_admin: Annotated[AdminContext, Depends(require_permission("disputes:read"))],
                   database: DatabaseDependency, status: str | None = Query(default=None, pattern="^(open|investigating|awaiting_customer|awaiting_vendor|resolved|closed)$"),
                   vendor_id: UUID | None = None, customer_id: UUID | None = None,
                   date_from: datetime | None = None, date_to: datetime | None = None,
                   minimum_amount: Decimal | None = Query(default=None, ge=0),
                   maximum_amount: Decimal | None = Query(default=None, ge=0),
                   reason: str | None = Query(default=None, max_length=160),
                   limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    if minimum_amount is not None and maximum_amount is not None and minimum_amount > maximum_amount:
        raise ApiError(422, "INVALID_AMOUNT_RANGE", "Minimum amount must not exceed maximum amount")
    if date_from is not None and date_to is not None and date_from >= date_to:
        raise ApiError(422, "INVALID_DATE_RANGE", "Start date must be before end date")
    return success(await AdminRepository(database.pool).disputes(
        status, limit, offset, vendor_id, customer_id, date_from, date_to, minimum_amount, maximum_amount, reason,
    ))


@router.post("/disputes")
async def create_dispute(payload: DisputeCreate, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("disputes:manage"))],
    database: DatabaseDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    repository = AdminRepository(database.pool)
    data = await repository.create_dispute(admin.user_id, admin.role_name, payload.booking_id, payload.reason,
                                           payload.description, _metadata(request), idempotency_key)
    return success(data, "Dispute opened")


@router.get("/disputes/{dispute_id}")
async def dispute_detail(dispute_id: UUID,
    _admin: Annotated[AdminContext, Depends(require_permission("disputes:read"))], database: DatabaseDependency
) -> dict[str, Any]:
    data = await AdminRepository(database.pool).dispute(dispute_id)
    if data is None:
        raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
    return success(data)


@router.post("/disputes/{dispute_id}/action")
async def dispute_action(dispute_id: UUID, payload: DisputeAction, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("disputes:manage"))],
    database: DatabaseDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    data = await AdminRepository(database.pool).dispute_action(admin.user_id, admin.role_name, dispute_id,
                                                                payload.action, payload.message, _metadata(request), idempotency_key)
    return success(data, "Dispute updated")


@router.post("/disputes/{dispute_id}/refund-request", status_code=202)
async def create_dispute_refund_request(
    dispute_id: UUID, payload: DisputeRefundCreate, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("refunds:create"))],
    database: DatabaseDependency,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> dict[str, Any]:
    repository = AdminRepository(database.pool)
    dispute = await repository.dispute(dispute_id)
    if dispute is None:
        raise ApiError(404, "DISPUTE_NOT_FOUND", "Dispute was not found")
    refund, created = await repository.create_refund_request(
        admin.user_id, UUID(str(dispute["booking_id"])), payload.amount_inr, payload.reason,
        idempotency_key, admin.role_name, _metadata(request), dispute_id,
    )
    return success(refund, "Refund request recorded for finance approval" if created else "Existing refund request returned")


@router.get("/audit-logs")
async def audit_logs(_admin: Annotated[AdminContext, Depends(require_permission("audit:read"))],
                     database: DatabaseDependency, entity_type: str | None = None, action: str | None = None,
                     entity_id: str | None = Query(default=None, max_length=100),
                     limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).audit(entity_type, action, entity_id, limit, offset))


@router.get("/financial-diagnostics")
async def financial_diagnostics(
    _admin: Annotated[AdminContext, Depends(require_permission("financial_diagnostics:read"))],
    database: DatabaseDependency,
) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).financial_diagnostics())


@router.get("/roles")
async def roles(_admin: Annotated[AdminContext, Depends(require_permission("roles:read"))],
                database: DatabaseDependency) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).role_matrix())


@router.get("/admin-users")
async def admin_users(_admin: Annotated[AdminContext, Depends(require_permission("admin_users:manage"))],
                      database: DatabaseDependency, limit: int = Query(default=50, ge=1, le=100),
                      offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    return success(await AdminRepository(database.pool).admin_users(limit, offset))


@router.patch("/admin-users/{user_id}")
async def update_admin_user(user_id: UUID, payload: AdminUserPatch, request: Request,
    admin: Annotated[AdminContext, Depends(require_permission("admin_users:manage"))], database: DatabaseDependency
) -> dict[str, Any]:
    data = await AdminRepository(database.pool).update_admin_user(admin.user_id, admin.role_name, user_id,
        payload.role_name, payload.is_active, payload.reason, _metadata(request))
    return success(data, "Administrator permissions updated")
