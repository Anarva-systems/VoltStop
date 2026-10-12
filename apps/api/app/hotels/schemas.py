from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoomTypeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    max_guests: int = Field(ge=1, le=12)
    base_rate_inr: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    total_rooms: int = Field(ge=1, le=10000)
    free_cancellation_hours: int = Field(default=24, ge=0, le=720)
    is_active: bool = True


class RoomTypePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    max_guests: int | None = Field(default=None, ge=1, le=12)
    base_rate_inr: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    total_rooms: int | None = Field(default=None, ge=1, le=10000)
    free_cancellation_hours: int | None = Field(default=None, ge=0, le=720)
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field in ("name", "max_guests", "base_rate_inr", "total_rooms", "free_cancellation_hours", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class InventoryUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stay_date: date
    room_capacity: int | None = Field(default=None, ge=0, le=10000)
    rooms_available: int = Field(ge=0, le=10000)
    nightly_rate_inr: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


class QuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    room_type_id: UUID
    check_in: date
    check_out: date
    guests: int = Field(ge=1, le=12)
    rooms: int = Field(default=1, ge=1, le=4)

    @model_validator(mode="after")
    def valid_dates(self):
        india_tz = timezone(timedelta(hours=5, minutes=30))
        if self.check_in < datetime.now(india_tz).date() or self.check_out <= self.check_in or (self.check_out - self.check_in).days > 30:
            raise ValueError("check_out must be after check_in and stays are limited to 30 nights")
        return self


class ReservationCreate(QuoteRequest):
    expected_amount_inr: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
