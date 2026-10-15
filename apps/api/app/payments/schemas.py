from pydantic import BaseModel, ConfigDict, Field


class RazorpayCheckoutVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    payment_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    signature: str = Field(min_length=64, max_length=128, pattern=r"^[a-fA-F0-9]+$")
