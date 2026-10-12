from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MenuOptionChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    price_delta_inr: Decimal = Field(default=Decimal("0"), ge=-100000, le=100000, max_digits=8, decimal_places=2)


class MenuOptionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    required: bool = False
    choices: list[MenuOptionChoice] = Field(min_length=1, max_length=20)


class MenuOptionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group: str = Field(min_length=1, max_length=60)
    choice: str = Field(min_length=1, max_length=60)


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=80)
    sort_order: int = Field(default=0, ge=0, le=10000)


class MenuItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: UUID
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    price_inr: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    is_available: bool = True
    options: list[MenuOptionGroup] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def validate_options(self):
        names = [item.name.strip().lower() for item in self.options]
        if len(names) != len(set(names)):
            raise ValueError("Option groups must have unique names")
        for group in self.options:
            choices = [item.name.strip().lower() for item in group.choices]
            if len(choices) != len(set(choices)):
                raise ValueError("Option choices must have unique names")
        return self


class MenuItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    price_inr: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    is_available: bool | None = None
    options: list[MenuOptionGroup] | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def validate_required_values(self):
        for field in ("category_id", "name", "price_inr", "is_available", "options"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.options is not None:
            names = [item.name.strip().lower() for item in self.options]
            if len(names) != len(set(names)):
                raise ValueError("Option groups must have unique names")
        return self


class OrderLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: UUID
    quantity: int = Field(ge=1, le=20)
    options: list[MenuOptionSelection] = Field(default_factory=list, max_length=10)


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor_id: UUID
    fulfillment_method: Literal["pickup"] = "pickup"
    items: list[OrderLineCreate] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_items(self):
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Combine quantities for duplicate menu items")
        return self


class OrderStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["accepted", "preparing", "ready", "completed"]
