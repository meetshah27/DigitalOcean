import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("app.request")

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_ctx.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _request_id_ctx.set(request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception as exc:
            # BaseHTTPMiddleware re-raises here rather than handing back the response FastAPI's
            # own Exception handler would build, so build it directly to keep the request-id
            # header and JSON logging line consistent for 500s too.
            from app.errors import unhandled_exception_handler

            response = await unhandled_exception_handler(request, exc)
        finally:
            _request_id_ctx.reset(token)

        duration_ms = round((time.monotonic() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request",
            extra={
                "extra_fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                }
            },
        )
        return response
