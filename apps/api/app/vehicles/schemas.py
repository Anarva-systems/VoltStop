from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.connectors import normalize_connectors

VehicleText = Annotated[str, StringConstraints(min_length=1, max_length=120, strip_whitespace=True)]


class VehicleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    make: VehicleText
    model: VehicleText
    vehicle_type: Annotated[str, StringConstraints(min_length=1, max_length=30, strip_whitespace=True)] = "car"
    battery_kwh: float = Field(gt=0, le=500)
    efficiency_km_per_kwh: float = Field(gt=0, le=20)
    current_soc: float | None = Field(default=None, ge=0, le=100)
    connector_compatibility: list[str] = Field(default_factory=list, max_length=8)
    max_charging_kw: float | None = Field(default=None, gt=0, le=1000)
    is_default: bool = False

    @field_validator("vehicle_type")
    @classmethod
    def valid_vehicle_type(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"car", "suv", "motorcycle", "other"}:
            raise ValueError("Vehicle type must be car, suv, motorcycle, or other")
        return normalized

    @field_validator("connector_compatibility")
    @classmethod
    def valid_connectors(cls, values: list[str]) -> list[str]:
        return normalize_connectors(values)


class VehiclePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    make: VehicleText | None = None
    model: VehicleText | None = None
    vehicle_type: Annotated[str, StringConstraints(min_length=1, max_length=30, strip_whitespace=True)] | None = None
    battery_kwh: float | None = Field(default=None, gt=0, le=500)
    efficiency_km_per_kwh: float | None = Field(default=None, gt=0, le=20)
    current_soc: float | None = Field(default=None, ge=0, le=100)
    connector_compatibility: list[str] | None = Field(default=None, max_length=8)
    max_charging_kw: float | None = Field(default=None, gt=0, le=1000)
    is_default: bool | None = None

    @field_validator("vehicle_type")
    @classmethod
    def valid_vehicle_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.lower()
        if normalized not in {"car", "suv", "motorcycle", "other"}:
            raise ValueError("Vehicle type must be car, suv, motorcycle, or other")
        return normalized

    @field_validator("connector_compatibility")
    @classmethod
    def valid_connectors(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return values
        return normalize_connectors(values)

    def changes(self) -> dict:
        changes = self.model_dump(exclude_unset=True)
        if not changes:
            raise ValueError("At least one vehicle field must be provided")
        return changes
