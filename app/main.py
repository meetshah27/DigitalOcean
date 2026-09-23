import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import close_db, init_db
from app.errors import unhandled_exception_handler
from app.logging_config import configure_logging
from app.middleware import RequestContextMiddleware
from app.routes.health import router as health_router
from app.routes.links import redirect_router
from app.routes.links import router as links_router

configure_logging(settings.log_level)
logger = logging.getLogger("app.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info(
        "startup",
        extra={"extra_fields": {"config": settings.model_dump()}},
    )
    yield
    close_db()
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="URL Shortener API", lifespan=lifespan)
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    # Order matters: /{code} is a catch-all path param and must be registered last,
    # otherwise it would shadow the exact-match routes below (/health, /ready, /links...).
    app.include_router(health_router)
    app.include_router(links_router)
    app.include_router(redirect_router)
    return app


app = create_app()
