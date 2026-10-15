from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from typing import Annotated
from datetime import datetime, timedelta, timezone

PlaceName = Annotated[str, StringConstraints(min_length=2, max_length=100, strip_whitespace=True)]


class RoutePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: PlaceName
    destination: PlaceName
    battery_kwh: float = Field(gt=0, le=500)
    current_soc: float = Field(ge=0, le=100, description="Current state of charge as a percentage")
    efficiency_km_per_kwh: float = Field(gt=0, le=20)
    persist: bool = True
    departure_at: datetime | None = None

    @field_validator("departure_at")
    @classmethod
    def departure_must_be_aware_and_not_past(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("departure_at must include a timezone")
        if value < datetime.now(timezone.utc) - timedelta(minutes=5):
            raise ValueError("departure_at cannot be in the past")
        return value.astimezone(timezone.utc)


class DriverTripRequest(BaseModel):
    """A driver-owned, scheduled corridor trip; not a passenger booking."""

    model_config = ConfigDict(extra="forbid")

    origin: PlaceName
    destination: PlaceName
    departure_at: datetime
    estimated_arrival_at: datetime | None = None
    vehicle_id: UUID
    current_soc: float | None = Field(default=None, ge=0, le=100)
    available_seats: int = Field(ge=1, le=8)
    notes: Annotated[str, StringConstraints(max_length=1000)] | None = None
    is_discoverable: bool = False

    @field_validator("departure_at", "estimated_arrival_at")
    @classmethod
    def timestamps_must_be_aware_and_normalized(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Trip timestamps must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("departure_at")
    @classmethod
    def departure_must_be_in_the_future(cls, value: datetime) -> datetime:
        if value <= datetime.now(timezone.utc):
            raise ValueError("departure_at must be in the future")
        return value

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        normalized = value.strip() if value is not None else None
        return normalized or None

    @model_validator(mode="after")
    def arrival_must_follow_departure(self) -> "DriverTripRequest":
        if (
            self.estimated_arrival_at is not None
            and self.estimated_arrival_at <= self.departure_at
        ):
            raise ValueError("estimated_arrival_at must be after departure_at")
        return self
