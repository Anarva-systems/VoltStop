from pydantic import BaseModel, ConfigDict, Field


class PushTokenRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(pattern=r"^[A-Za-z0-9_:=-]{16,512}$")
    platform: str = Field(pattern=r"^(android|ios|web)$")
