from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated

PlaceName = Annotated[str, StringConstraints(min_length=2, max_length=100, strip_whitespace=True)]


class RoutePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin: PlaceName
    destination: PlaceName
    battery_kwh: float = Field(gt=0, le=500)
    current_soc: float = Field(ge=0, le=100, description="Current state of charge as a percentage")
    efficiency_km_per_kwh: float = Field(gt=0, le=20)
    persist: bool = True
