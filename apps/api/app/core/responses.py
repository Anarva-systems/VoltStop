from typing import Any

from fastapi.responses import JSONResponse


def success(data: Any, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "data": data, "message": message}


def error_response(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message}},
    )
