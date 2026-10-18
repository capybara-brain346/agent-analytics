from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from src.config import Settings

_pool: AsyncConnectionPool | None = None


async def open_pool(settings: Settings) -> None:
    global _pool
    _pool = AsyncConnectionPool(
        settings.database_url,
        max_size=settings.db_pool_max_size,
        kwargs={"options": "-c TimeZone=UTC"},  # date_trunc and casts must not depend on the server
        open=False,
    )
    await _pool.open(wait=False)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool is not open")
    return _pool


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    # One transaction: commit on a normal exit, rollback on an exception.
    async with pool().connection() as conn:
        yield conn
