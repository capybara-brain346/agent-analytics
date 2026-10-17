from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import get_settings
from src.logger import configure_logging, get_logger
from src.routes import api_router, root_router
from src.store import db

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    await db.open_pool(settings)
    if not settings.api_token:
        log.warning(
            "API_TOKEN is not set: /api/* is open. Set it, or restrict /api at the ingress."
        )
    log.info("api started")
    yield
    await db.close_pool()


def create_app() -> FastAPI:
    app = FastAPI(title="Agent Analytics API", lifespan=lifespan)
    app.include_router(root_router)
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
