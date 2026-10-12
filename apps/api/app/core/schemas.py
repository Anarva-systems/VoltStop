from typing import Any

from pydantic import BaseModel


class ApiSuccess(BaseModel):
    success: bool = True
    data: Any
    message: str = "OK"
