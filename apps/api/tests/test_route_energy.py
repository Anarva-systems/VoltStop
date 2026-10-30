from app.routes.energy import (
    EnergyThresholds,
    assess_charging_stop,
    estimate_trip_energy,
    hospitality_candidates,
)

THRESHOLDS = EnergyThresholds(
    derate=0.85,
    safety_buffer_soc_pct=15.0,
    target_charge_soc_pct=80.0,
    window_high_soc_pct=35.0,
    window_low_soc_pct=20.0,
)


def test_derate_lowers_efficiency_and_raises_consumption():
    result = estimate_trip_energy(
        distance_km=100, battery_kwh=60, current_soc=80,
        efficiency_km_per_kwh=6, thresholds=THRESHOLDS,
    )
    assert result["real_world_efficiency_km_per_kwh"] == 5.1
    assert result["estimated_consumption_kwh"] == 19.61
    assert result["estimated_remaining_soc"] == 47.32
    assert result["requires_charging_stop"] is False
    assert result["unreachable_without_charge"] is False


def test_usable_range_stops_at_the_safety_buffer():
    result = estimate_trip_energy(
        distance_km=400, battery_kwh=60, current_soc=80,
        efficiency_km_per_kwh=6, thresholds=THRESHOLDS,
    )
    # (80 - 15) % of 60 kWh at 5.1 km/kWh.
    assert result["usable_range_km"] == round(0.65 * 60 * 5.1, 2)
    assert result["requires_charging_stop"] is True
    assert result["unreachable_without_charge"] is True
    assert result["estimated_remaining_soc"] < 0


def test_charging_window_sits_between_the_configured_soc_levels():
    result = estimate_trip_energy(
        distance_km=300, battery_kwh=40, current_soc=90,
        efficiency_km_per_kwh=6, thresholds=THRESHOLDS,
    )
    window = result["optimal_charging_window"]
    effective = 6 * 0.85
    assert window["start_km"] == round((90 - 35) / 100 * 40 * effective, 2)
    assert window["end_km"] == round((90 - 20) / 100 * 40 * effective, 2)
    assert window["start_km"] < window["end_km"]


def test_window_offsets_are_clamped_when_already_below_the_window():
    result = estimate_trip_energy(
        distance_km=300, battery_kwh=40, current_soc=18,
        efficiency_km_per_kwh=6, thresholds=THRESHOLDS,
    )
    window = result["optimal_charging_window"]
    assert window["start_km"] == 0.0
    assert window["end_km"] == 0.0
    # Only the 3 % above the safety buffer is usable.
    assert result["usable_range_km"] == round(0.03 * 40 * 5.1, 2)


def _stop(**overrides):
    stop = {
        "vendor": {"id": "vendor-1", "name": "Highway Charger"},
        "distance_km": 1.2,
        "route_progress": 0.4,
        "connector_match": "exact",
        "services": [{"service_type": "food"}, {"service_type": "charging"}],
        "charging": [{"id": "unit-1", "supported_connectors": ["CCS2"], "max_power_kw": 120}],
    }
    stop.update(overrides)
    return stop


def test_stop_is_placed_on_the_route_and_sized_to_the_vehicle():
    assessed = assess_charging_stop(
        _stop(route_progress=0.75),
        distance_km=200, battery_kwh=60, current_soc=80,
        effective_efficiency=5.1, vehicle_max_charging_kw=50, thresholds=THRESHOLDS,
    )
    assert assessed["stop_placement_km"] == 150.0
    assert assessed["estimated_arrival_soc"] == 30.98
    assert assessed["in_optimal_charging_window"] is True
    assert assessed["charge_power_kw"] == 50
    assert assessed["charge_power_is_capped_by"] == "vehicle"
    # 60 kWh at 30.98 % charged to 80 % on a 50 kW intake is about 59 minutes.
    assert assessed["estimated_charge_kwh"] == 29.41
    assert assessed["estimated_charge_minutes"] == 35


def test_early_stop_is_outside_the_charging_window():
    assessed = assess_charging_stop(
        _stop(),
        distance_km=200, battery_kwh=60, current_soc=80,
        effective_efficiency=5.1, vehicle_max_charging_kw=50, thresholds=THRESHOLDS,
    )
    assert assessed["stop_placement_km"] == 80.0
    assert assessed["estimated_arrival_soc"] == 53.86
    assert assessed["in_optimal_charging_window"] is False


def test_station_power_caps_when_the_vehicle_accepts_more():
    assessed = assess_charging_stop(
        _stop(charging=[{"id": "unit-1", "supported_connectors": ["CCS2"], "max_power_kw": 30}]),
        distance_km=200, battery_kwh=60, current_soc=80,
        effective_efficiency=5.1, vehicle_max_charging_kw=100, thresholds=THRESHOLDS,
    )
    assert assessed["charge_power_kw"] == 30
    assert assessed["charge_power_is_capped_by"] == "station"


def test_unknown_power_yields_no_invented_charge_time():
    assessed = assess_charging_stop(
        _stop(charging=[{"id": "unit-1", "supported_connectors": [], "max_power_kw": None}]),
        distance_km=200, battery_kwh=60, current_soc=80,
        effective_efficiency=5.1, vehicle_max_charging_kw=None, thresholds=THRESHOLDS,
    )
    assert assessed["charge_power_kw"] is None
    assert assessed["estimated_charge_minutes"] is None


def test_stop_beyond_the_destination_is_flagged():
    assessed = assess_charging_stop(
        _stop(route_progress=1.4),
        distance_km=100, battery_kwh=60, current_soc=80,
        effective_efficiency=5.1, vehicle_max_charging_kw=50, thresholds=THRESHOLDS,
    )
    assert assessed["reaches_route_before_arrival"] is False


def test_hospitality_candidates_keep_only_places_to_eat_or_rest():
    nearby = [
        {
            "vendor": {"id": "a", "name": "Dhaba", "type": "restaurant"},
            "distance_km": 0.4,
            "services": [{"service_type": "food"}],
            "available_slots": [],
        },
        {
            "vendor": {"id": "b", "name": "Other Charger", "type": "hotel"},
            "distance_km": 0.9,
            "services": [{"service_type": "charging"}],
            "available_slots": [],
        },
        {
            "vendor": {"id": "c", "name": "Transit Inn", "type": "hotel"},
            "distance_km": 1.5,
            "services": [{"service_type": "room"}],
            "available_slots": [{"id": "slot-1"}],
        },
    ]
    companions = hospitality_candidates(nearby, exclude_vendor_id="b")
    assert [companion["name"] for companion in companions] == ["Dhaba", "Transit Inn"]
    assert companions[1]["available_slots"] == [{"id": "slot-1"}]
