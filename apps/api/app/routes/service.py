import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import ApiError

PILOT_PLACES = {
    "srikakulam": "Srikakulam, Andhra Pradesh, India",
    "vizianagaram": "Vizianagaram, Andhra Pradesh, India",
    "visakhapatnam": "Visakhapatnam, Andhra Pradesh, India",
    "anakapalle": "Anakapalle, Andhra Pradesh, India",
    "tuni": "Tuni, Andhra Pradesh, India",
    "annavaram": "Annavaram, Andhra Pradesh, India",
    "rajahmundry": "Rajahmundry, Andhra Pradesh, India",
    "eluru": "Eluru, Andhra Pradesh, India",
    "vijayawada": "Vijayawada, Andhra Pradesh, India",
}

PILOT_COORDINATES = {
    "srikakulam": (83.8968, 18.2969),
    "vizianagaram": (83.3970, 18.1133),
    "visakhapatnam": (83.20161, 17.68009),
    "anakapalle": (83.003946, 17.691342),
    "tuni": (82.5460, 17.3590),
    "annavaram": (82.396713, 17.279295),
    "rajahmundry": (81.777839, 17.005171),
    "eluru": (81.1154, 16.7104),
    "vijayawada": (80.6480, 16.5062),
}


@dataclass(frozen=True)
class RouteResult:
    distance_meters: int
    geojson: str
    provider: str
    duration_seconds: int | None = None


class RouteProvider(Protocol):
    async def route(self, origin: str, destination: str) -> RouteResult: ...


class OpenStreetMapRouteProvider:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def route(self, origin: str, destination: str) -> RouteResult:
        origin_key = origin.strip().split(",", 1)[0].strip().casefold()
        dest_key = destination.strip().split(",", 1)[0].strip().casefold()

        if origin_key in PILOT_COORDINATES and dest_key in PILOT_COORDINATES:
            lon1, lat1 = PILOT_COORDINATES[origin_key]
            lon2, lat2 = PILOT_COORDINATES[dest_key]
        else:
            lon1, lat1 = 83.8968, 18.2969
            lon2, lat2 = 80.6480, 16.5062

        osrm_base = self.settings.osrm_router_url.rstrip("/")
        osrm_url = f"{osrm_base}/{lon1},{lat1};{lon2},{lat2}"
        try:
            response = await self.client.get(
                osrm_url,
                params={"overview": "full", "geometries": "geojson"},
                timeout=10.0,
            )
        except httpx.RequestError as exc:
            raise ApiError(503, "ROUTE_PROVIDER_UNAVAILABLE", "OpenStreetMap Routes could not be reached") from exc

        if response.is_error:
            raise ApiError(502, "ROUTE_PROVIDER_ERROR", "OpenStreetMap Routes could not calculate this route")

        try:
            data = response.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                raise ValueError("No route found")
            route_data = data["routes"][0]
            distance = int(route_data["distance"])
            geometry = route_data["geometry"]
            if geometry.get("type") != "LineString" or not geometry.get("coordinates"):
                raise ValueError("Route geometry missing")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ApiError(502, "ROUTE_PROVIDER_ERROR", "OpenStreetMap Routes returned incomplete route data") from exc

        duration = route_data.get("duration")
        duration_seconds = int(round(duration)) if isinstance(duration, (int, float)) and duration > 0 else None
        return RouteResult(distance, json.dumps(geometry), "openstreetmap", duration_seconds)


class GoogleRoutesProvider:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def route(self, origin: str, destination: str) -> RouteResult:
        if not self.settings.google_maps_api_key:
            raise ApiError(503, "ROUTE_PROVIDER_UNAVAILABLE", "Google Routes is not configured")
        try:
            response = await self.client.post(
                self.settings.google_routes_url,
                headers={
                    "X-Goog-Api-Key": self.settings.google_maps_api_key,
                    "X-Goog-FieldMask": "routes.distanceMeters,routes.duration,routes.polyline.geoJsonLinestring",
                },
                json={
                    "origin": {"address": origin},
                    "destination": {"address": destination},
                    "travelMode": "DRIVE",
                    "routingPreference": "TRAFFIC_UNAWARE",
                },
            )
        except httpx.RequestError as exc:
            raise ApiError(503, "ROUTE_PROVIDER_UNAVAILABLE", "Google Routes could not be reached") from exc
        if response.is_error:
            raise ApiError(502, "ROUTE_PROVIDER_ERROR", "Google Routes could not calculate this route")
        try:
            route = response.json()["routes"][0]
            distance = int(route["distanceMeters"])
            line = route["polyline"]["geoJsonLinestring"]
            if line.get("type") != "LineString" or not line.get("coordinates"):
                raise ValueError("route geometry missing")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ApiError(502, "ROUTE_PROVIDER_ERROR", "Google Routes returned incomplete route data") from exc
        duration_value = route.get("duration")
        duration_seconds = None
        if isinstance(duration_value, str) and duration_value.endswith("s"):
            try:
                duration_seconds = max(1, int(float(duration_value[:-1])))
            except ValueError:
                duration_seconds = None
        return RouteResult(distance, json.dumps(line), "google_routes", duration_seconds)


class PilotRouteService:
    def __init__(self, provider: RouteProvider) -> None:
        self.provider = provider

    async def plan(
        self,
        origin: str,
        destination: str,
        battery_kwh: float,
        current_soc: float,
        efficiency_km_per_kwh: float,
        database: Any,
    ) -> dict[str, Any]:
        origin_key = origin.strip().split(",", 1)[0].strip().casefold()
        destination_key = destination.strip().split(",", 1)[0].strip().casefold()
        if origin_key not in PILOT_PLACES or destination_key not in PILOT_PLACES:
            raise ApiError(
                422,
                "UNSUPPORTED_PILOT_ROUTE",
                "Choose stops on the supported Srikakulam–Vijayawada NH-16 corridor",
            )
        if origin_key == destination_key:
            raise ApiError(422, "INVALID_ROUTE", "Origin and destination must be different")

        result = await self.provider.route(PILOT_PLACES[origin_key], PILOT_PLACES[destination_key])
        distance_km = result.distance_meters / 1000.0
        consumption_kwh = distance_km / efficiency_km_per_kwh
        remaining_soc = current_soc - (consumption_kwh / battery_kwh * 100)
        stops = await database.recommended_route_vendors(result.geojson)
        response = {
            "origin": PILOT_PLACES[origin_key],
            "destination": PILOT_PLACES[destination_key],
            "route": "NH-16",
            "distance_km": round(distance_km, 2),
            "distance_source": result.provider,
            "estimated_consumption_kwh": round(consumption_kwh, 2),
            "estimated_remaining_soc": round(remaining_soc, 2),
            "route_coordinates": json.loads(result.geojson).get("coordinates", []),
            "recommended_pitstops": stops,
        }
        if result.duration_seconds is not None:
            response["estimated_duration_seconds"] = result.duration_seconds
        return response
