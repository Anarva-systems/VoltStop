"""Route energy and charging-window math.

Kept out of controllers and repositories so the physics has one home and can be
tested without a database or a route provider.
"""

from dataclasses import dataclass
from typing import Any

HOSPITALITY_SERVICE_TYPES = frozenset({"food", "room", "sleep_and_charge", "rest_area"})


@dataclass(frozen=True)
class EnergyThresholds:
    derate: float
    safety_buffer_soc_pct: float
    target_charge_soc_pct: float
    window_high_soc_pct: float
    window_low_soc_pct: float

    @classmethod
    def from_settings(cls, settings: Any) -> "EnergyThresholds":
        return cls(
            derate=settings.ev_efficiency_derate,
            safety_buffer_soc_pct=settings.ev_safety_buffer_soc_pct,
            target_charge_soc_pct=settings.ev_target_charge_soc_pct,
            window_high_soc_pct=settings.ev_charging_window_high_soc_pct,
            window_low_soc_pct=settings.ev_charging_window_low_soc_pct,
        )


def distance_at_soc(
    soc_pct: float,
    *,
    current_soc: float,
    battery_kwh: float,
    effective_efficiency: float,
) -> float:
    """Kilometres along the route where SoC crosses the given level.

    Negative means the vehicle is already below that level at departure.
    """
    return (current_soc - soc_pct) / 100.0 * battery_kwh * effective_efficiency


def estimate_trip_energy(
    *,
    distance_km: float,
    battery_kwh: float,
    current_soc: float,
    efficiency_km_per_kwh: float,
    thresholds: EnergyThresholds,
) -> dict[str, Any]:
    effective_efficiency = efficiency_km_per_kwh * thresholds.derate
    consumption_kwh = distance_km / effective_efficiency
    remaining_soc = current_soc - (consumption_kwh / battery_kwh * 100)
    usable_range_km = distance_at_soc(
        thresholds.safety_buffer_soc_pct,
        current_soc=current_soc,
        battery_kwh=battery_kwh,
        effective_efficiency=effective_efficiency,
    )
    window_start_km = distance_at_soc(
        thresholds.window_high_soc_pct,
        current_soc=current_soc,
        battery_kwh=battery_kwh,
        effective_efficiency=effective_efficiency,
    )
    window_end_km = distance_at_soc(
        thresholds.window_low_soc_pct,
        current_soc=current_soc,
        battery_kwh=battery_kwh,
        effective_efficiency=effective_efficiency,
    )
    return {
        "distance_km": round(distance_km, 2),
        "real_world_efficiency_km_per_kwh": round(effective_efficiency, 3),
        "efficiency_derate": thresholds.derate,
        "safety_buffer_soc_pct": thresholds.safety_buffer_soc_pct,
        "estimated_consumption_kwh": round(consumption_kwh, 2),
        "estimated_remaining_soc": round(remaining_soc, 2),
        "usable_range_km": round(max(0.0, usable_range_km), 2),
        "requires_charging_stop": remaining_soc < thresholds.safety_buffer_soc_pct,
        "unreachable_without_charge": remaining_soc <= 0,
        "optimal_charging_window": {
            "from_soc_pct": thresholds.window_high_soc_pct,
            "to_soc_pct": thresholds.window_low_soc_pct,
            "start_km": round(max(0.0, window_start_km), 2),
            "end_km": round(max(0.0, window_end_km), 2),
        },
    }


def assess_charging_stop(
    stop: dict[str, Any],
    *,
    distance_km: float,
    battery_kwh: float,
    current_soc: float,
    effective_efficiency: float,
    vehicle_max_charging_kw: float | None,
    thresholds: EnergyThresholds,
) -> dict[str, Any]:
    """Place a corridor stop on the route timeline and price its charge time.

    Charge minutes are a linear approximation of the constant-current phase and
    deliberately stop at the configured target SoC, below where taper begins.
    """
    route_progress = stop.get("route_progress")
    if route_progress is None:
        return {**stop, "stop_placement_km": None, "estimated_arrival_soc": None}

    stop_km = float(route_progress) * distance_km
    arrival_soc = current_soc - (stop_km / effective_efficiency) / battery_kwh * 100
    power_options = [
        value
        for value in (vehicle_max_charging_kw, _stop_power_kw(stop))
        if value is not None and value > 0
    ]
    effective_kw = min(power_options) if power_options else None
    energy_to_target_kwh = max(
        0.0, (thresholds.target_charge_soc_pct - max(arrival_soc, 0.0)) / 100.0 * battery_kwh
    )
    in_window = (
        thresholds.window_high_soc_pct >= arrival_soc >= thresholds.window_low_soc_pct
    )
    return {
        **stop,
        "stop_placement_km": round(stop_km, 2),
        "estimated_arrival_soc": round(arrival_soc, 2),
        "reaches_route_before_arrival": stop_km <= distance_km,
        "arrives_with_charge_remaining": arrival_soc > 0,
        "in_optimal_charging_window": in_window,
        "charge_power_kw": round(effective_kw, 2) if effective_kw else None,
        "charge_power_is_capped_by": _power_cap(vehicle_max_charging_kw, _stop_power_kw(stop)),
        "estimated_charge_minutes": (
            round(energy_to_target_kwh / effective_kw * 60) if effective_kw else None
        ),
        "estimated_charge_kwh": round(energy_to_target_kwh, 2),
    }


def hospitality_candidates(stops: list[dict[str, Any]], *, exclude_vendor_id: Any = None) -> list[dict[str, Any]]:
    """Reduce nearby vendor rows to the places a driver can eat or rest."""
    companions: list[dict[str, Any]] = []
    for stop in stops:
        vendor = stop.get("vendor") or {}
        vendor_id = vendor.get("id")
        if exclude_vendor_id is not None and vendor_id == str(exclude_vendor_id):
            continue
        services = [
            service
            for service in (stop.get("services") or [])
            if service.get("service_type") in HOSPITALITY_SERVICE_TYPES
        ]
        if not services:
            continue
        companions.append({
            "id": vendor_id,
            "name": vendor.get("name"),
            "type": vendor.get("type"),
            "lat": vendor.get("lat"),
            "lng": vendor.get("lng"),
            "address": vendor.get("address"),
            "distance_km": round(float(stop.get("distance_km") or 0), 2),
            "services": services,
            "available_slots": stop.get("available_slots") or [],
        })
    return companions


def _stop_power_kw(stop: dict[str, Any]) -> float | None:
    values = [
        float(unit["max_power_kw"])
        for unit in (stop.get("charging") or [])
        if unit.get("max_power_kw")
    ]
    return max(values) if values else None


def _power_cap(vehicle_max_kw: float | None, station_max_kw: float | None) -> str | None:
    if vehicle_max_kw is None or station_max_kw is None:
        return None
    if vehicle_max_kw <= station_max_kw:
        return "vehicle"
    return "station"
