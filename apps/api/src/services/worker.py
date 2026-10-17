"""Worker loop: 1-min tick, take the due site that waited longest, run its lane (7.1, 7.9)."""

import asyncio

from src.config import get_settings
from src.logger import get_logger
from src.store import db

log = get_logger(__name__)


async def tick() -> None:
    raise NotImplementedError


async def run_forever() -> None:
    settings = get_settings()
    await db.open_pool(settings)
    log.info("worker started", extra={"tick_seconds": settings.tick_seconds})
    try:
        while True:
            try:
                await tick()
            except NotImplementedError:
                log.warning("worker tick not implemented")
            await asyncio.sleep(settings.tick_seconds)
    finally:
        await db.close_pool()
