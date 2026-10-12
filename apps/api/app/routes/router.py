from typing import Any

import httpx
from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.database_dependency import DatabaseDependency
from app.core.dependencies import get_http_client
from app.core.responses import success
from app.auth.dependencies import CurrentUser
from app.routes.schemas import RoutePlanRequest
from app.routes.service import OpenStreetMapRouteProvider, PilotRouteService

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
    if payload.persist:
        route_id = await database.save_driver_route(user.id, payload, result)
        result["route_id"] = str(route_id)
    return success(result)
