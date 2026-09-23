import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app.middleware import get_request_id

logger = logging.getLogger("app.error")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = get_request_id()
    logger.error(
        "unhandled_exception",
        exc_info=exc,
        extra={"extra_fields": {"request_id": request_id, "path": request.url.path}},
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "request_id": request_id},
    )
