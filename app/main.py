import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import close_db, init_db
from app.errors import unhandled_exception_handler
from app.logging_config import configure_logging
from app.middleware import RequestContextMiddleware
from app.routes.health import router as health_router

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
    app.include_router(health_router)
    return app


app = create_app()
