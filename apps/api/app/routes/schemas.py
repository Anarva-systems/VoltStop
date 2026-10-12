from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
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
