from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    car_model: str | None = Field(default=None, max_length=120)
    battery_kwh: Decimal | None = Field(default=None, gt=0, le=500)
    default_efficiency_km_per_kwh: Decimal | None = Field(default=None, gt=0, le=20)
    current_soc: Decimal | None = Field(default=None, ge=0, le=100)

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)
