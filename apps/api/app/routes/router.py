import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, Query

from app.core.config import Settings, get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.dependencies import get_http_client
from app.core.errors import ApiError
from app.core.responses import success
from app.auth.dependencies import CurrentUser
from app.routes.schemas import DriverTripRequest, RoutePlanRequest
from app.routes.service import OpenStreetMapRouteProvider, PILOT_PLACES, PilotRouteService

router = APIRouter(prefix="/routes", tags=["routes"])


def route_service(
    client: httpx.AsyncClient = Depends(get_http_client),
    settings: Settings = Depends(get_settings),
) -> PilotRouteService:
    return PilotRouteService(OpenStreetMapRouteProvider(client, settings))


@router.post("/plan")
async def plan_route(
    payload: RoutePlanRequest,
    user: CurrentUser,
    database: DatabaseDependency,
    service: PilotRouteService = Depends(route_service),
) -> dict[str, Any]:
    result = await service.plan(
        payload.origin,
        payload.destination,
        payload.battery_kwh,
        payload.current_soc,
        payload.efficiency_km_per_kwh,
        database,
    )
    result["departure_at"] = payload.departure_at.isoformat() if payload.departure_at else None
    if payload.persist:
        route_id = await database.save_driver_route(user.id, payload, result)
        result["route_id"] = str(route_id)
    return success(result)


def _canonical_trip_place(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().split(",", 1)[0].strip().casefold()
    place = PILOT_PLACES.get(key)
    if place is None:
        raise ApiError(422, "UNSUPPORTED_PILOT_ROUTE", "Choose a supported NH-16 pilot stop")
    return place


def _trip_values(payload: DriverTripRequest) -> dict[str, Any]:
    return payload.model_dump()


def _trip_fingerprint(payload: DriverTripRequest) -> str:
    canonical = json.dumps(payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _plan_trip_if_possible(
    payload: DriverTripRequest,
    vehicle: dict[str, Any],
    database: Any,
    service: PilotRouteService,
) -> tuple[dict[str, Any] | None, str]:
    if payload.current_soc is None:
        return None, "not_requested"
    try:
        planned = await service.plan(
            payload.origin,
            payload.destination,
            float(vehicle["battery_kwh"]),
            payload.current_soc,
            float(vehicle["efficiency_km_per_kwh"]),
            database,
        )
        planned["departure_at"] = payload.departure_at.isoformat()
        return planned, "available"
    except ApiError as error:
        if error.status_code in (502, 503):
            return None, "unavailable"
        raise


@router.post("/trips")
async def create_driver_trip(
    payload: DriverTripRequest,
    user: CurrentUser,
    database: DatabaseDependency,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    service: PilotRouteService = Depends(route_service),
) -> dict[str, Any]:
    origin = _canonical_trip_place(payload.origin)
    destination = _canonical_trip_place(payload.destination)
    if origin == destination:
        raise ApiError(422, "INVALID_ROUTE", "Origin and destination must be different")

    # The saved vehicle is a server-verified driver-owned resource. The client
    # cannot supply a different driver or vehicle owner ID.
    vehicle = await database.driver_vehicle(user.id, payload.vehicle_id)
    if vehicle is None:
        raise ApiError(404, "VEHICLE_NOT_FOUND", "Choose one of your saved vehicles")
    route_plan, route_status = await _plan_trip_if_possible(payload, vehicle, database, service)
    values = _trip_values(payload)
    values["origin"] = origin
    values["destination"] = destination
    trip = await database.create_driver_trip(
        user.id,
        values,
        idempotency_key,
        _trip_fingerprint(payload),
        route_plan,
    )
    trip["route_plan_status"] = "available" if trip.get("route_plan") else route_status
    trip["recommended_pitstops"] = route_plan.get("recommended_pitstops", []) if route_plan else []
    return success(trip, "Trip scheduled")


@router.get("/trips")
async def list_driver_trips(
    user: CurrentUser,
    database: DatabaseDependency,
    bucket: str = Query("upcoming", pattern="^(upcoming|past|all)$"),
) -> dict[str, Any]:
    return success(await database.driver_trips(user.id, bucket))


@router.get("/trips/discover")
async def discover_driver_trips(
    user: CurrentUser,
    database: DatabaseDependency,
    origin: str | None = Query(None, min_length=2, max_length=100),
    destination: str | None = Query(None, min_length=2, max_length=100),
    departure_from: datetime | None = None,
    departure_before: datetime | None = None,
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    if departure_from is not None and (departure_from.tzinfo is None or departure_from.utcoffset() is None):
        raise ApiError(422, "INVALID_TRIP_DATE", "departure_from must include a timezone")
    if departure_before is not None and (departure_before.tzinfo is None or departure_before.utcoffset() is None):
        raise ApiError(422, "INVALID_TRIP_DATE", "departure_before must include a timezone")
    departure_from = departure_from.astimezone(timezone.utc) if departure_from else None
    departure_before = departure_before.astimezone(timezone.utc) if departure_before else None
    if departure_from is not None and departure_before is not None and departure_before <= departure_from:
        raise ApiError(422, "INVALID_TRIP_DATE", "departure_before must be after departure_from")

    return success(await database.discover_driver_trips(
        user.id,
        _canonical_trip_place(origin),
        _canonical_trip_place(destination),
        departure_from,
        departure_before,
        limit,
    ))


@router.get("/trips/{trip_id}")
async def get_driver_trip(
    trip_id: UUID,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    trip = await database.driver_trip(user.id, trip_id)
    if trip is None:
        raise ApiError(404, "TRIP_NOT_FOUND", "Trip was not found")
    if trip.get("route_plan") and trip["route_plan"].get("route_geojson"):
        geojson = trip["route_plan"]["route_geojson"]
        if isinstance(geojson, str):
            geojson = json.loads(geojson)
        trip["recommended_pitstops"] = await database.recommended_route_vendors(json.dumps(geojson))
        trip["route_plan_status"] = "available"
    else:
        trip["recommended_pitstops"] = []
        trip["route_plan_status"] = "unavailable"
    return success(trip)


@router.put("/trips/{trip_id}")
async def update_driver_trip(
    trip_id: UUID,
    payload: DriverTripRequest,
    user: CurrentUser,
    database: DatabaseDependency,
    service: PilotRouteService = Depends(route_service),
) -> dict[str, Any]:
    origin = _canonical_trip_place(payload.origin)
    destination = _canonical_trip_place(payload.destination)
    if origin == destination:
        raise ApiError(422, "INVALID_ROUTE", "Origin and destination must be different")
    vehicle = await database.driver_vehicle(user.id, payload.vehicle_id)
    if vehicle is None:
        raise ApiError(404, "VEHICLE_NOT_FOUND", "Choose one of your saved vehicles")
    route_plan, route_status = await _plan_trip_if_possible(payload, vehicle, database, service)
    values = _trip_values(payload)
    values["origin"] = origin
    values["destination"] = destination
    trip = await database.update_driver_trip(user.id, trip_id, values, route_plan)
    if trip is None:
        raise ApiError(404, "TRIP_NOT_FOUND", "Trip was not found")
    trip["route_plan_status"] = route_status
    trip["recommended_pitstops"] = route_plan.get("recommended_pitstops", []) if route_plan else []
    return success(trip, "Trip updated")


@router.post("/trips/{trip_id}/start")
async def start_driver_trip(
    trip_id: UUID,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    trip = await database.transition_driver_trip(user.id, trip_id, "in_progress")
    if trip is None:
        raise ApiError(404, "TRIP_NOT_FOUND", "Trip was not found")
    return success(trip, "Trip started")


@router.post("/trips/{trip_id}/complete")
async def complete_driver_trip(
    trip_id: UUID,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    trip = await database.transition_driver_trip(user.id, trip_id, "completed")
    if trip is None:
        raise ApiError(404, "TRIP_NOT_FOUND", "Trip was not found")
    return success(trip, "Trip completed")


@router.post("/trips/{trip_id}/cancel")
async def cancel_driver_trip(
    trip_id: UUID,
    user: CurrentUser,
    database: DatabaseDependency,
) -> dict[str, Any]:
    trip = await database.transition_driver_trip(user.id, trip_id, "cancelled")
    if trip is None:
        raise ApiError(404, "TRIP_NOT_FOUND", "Trip was not found")
    return success(trip, "Trip cancelled")
