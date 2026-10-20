from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ServiceType = Literal["food", "charging", "sleep_and_charge", "room", "parking", "rest_area"]


class VendorProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    type: Literal["restaurant", "hotel"] | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    description: str | None = Field(default=None, max_length=4000)
    image_url: str | None = Field(default=None, max_length=2000, pattern=r"^https?://")
    operating_hours: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def required_profile_fields_not_null(self):
        for field in ("name", "type", "address", "lat", "lng"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class VendorProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    type: Literal["restaurant", "hotel"]
    phone: str | None = Field(default=None, max_length=40)
    address: str = Field(min_length=1, max_length=500)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    description: str | None = Field(default=None, max_length=4000)
    image_url: str | None = Field(default=None, max_length=2000, pattern=r"^https?://")
    operating_hours: str | None = Field(default=None, max_length=1000)


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_type: ServiceType
    display_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price_inr: float = Field(ge=0)
    capacity: int | None = Field(default=None, ge=1)
    availability: dict[str, object] = Field(default_factory=dict)
    is_active: bool = True


class ServicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_type: ServiceType | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price_inr: float | None = Field(default=None, ge=0)
    capacity: int | None = Field(default=None, ge=1)
    availability: dict[str, object] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def non_nullable_fields_not_null(self):
        for field in ("service_type", "display_name", "price_inr", "availability", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class SlotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_start_time: datetime
    slot_end_time: datetime
    capacity: int = Field(ge=1, le=10000)
    price_inr: float = Field(ge=0)
    service_type: ServiceType = "charging"

    @model_validator(mode="after")
    def end_after_start(self):
        if self.slot_start_time.utcoffset() is None or self.slot_end_time.utcoffset() is None:
            raise ValueError("Slot times must include a timezone")
        if self.slot_start_time <= datetime.now(timezone.utc):
            raise ValueError("Slot start must be in the future")
        if self.slot_end_time <= self.slot_start_time:
            raise ValueError("Slot end must be after slot start")
        return self


class SlotPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_start_time: datetime | None = None
    slot_end_time: datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=10000)
    price_inr: float | None = Field(default=None, ge=0)
    service_type: ServiceType | None = None
    status: Literal["available", "closed"] | None = None

    @model_validator(mode="after")
    def timezone_aware(self):
        for field in ("slot_start_time", "slot_end_time", "capacity", "price_inr", "service_type", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        for value in (self.slot_start_time, self.slot_end_time):
            if value is not None and value.utcoffset() is None:
                raise ValueError("Slot times must include a timezone")
        return self


class BookingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000)
