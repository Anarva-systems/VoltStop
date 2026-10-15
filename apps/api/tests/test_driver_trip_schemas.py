from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.routes.schemas import DriverTripRequest


def _payload(**changes):
    departure = datetime.now(timezone.utc) + timedelta(days=1)
    return {
        "origin": "Srikakulam",
        "destination": "Vijayawada",
        "departure_at": departure,
        "estimated_arrival_at": departure + timedelta(hours=6),
        "vehicle_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
        "available_seats": 3,
        "notes": "  private note  ",
        "is_discoverable": False,
        **changes,
    }


def test_driver_trip_schema_normalizes_times_and_private_notes():
    request = DriverTripRequest.model_validate(_payload())
    assert request.departure_at.tzinfo == timezone.utc
    assert request.estimated_arrival_at > request.departure_at
    assert request.notes == "private note"


@pytest.mark.parametrize(
    "changes",
    [
        {"available_seats": 0},
        {"available_seats": 9},
        {"departure_at": "2030-01-01T12:00:00"},
        {"departure_at": datetime.now(timezone.utc) - timedelta(minutes=1)},
        {
            "estimated_arrival_at": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        {"notes": "x" * 1001},
        {"driver_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
    ],
)
def test_driver_trip_schema_rejects_invalid_inputs(changes):
    with pytest.raises(ValidationError):
        DriverTripRequest.model_validate(_payload(**changes))
