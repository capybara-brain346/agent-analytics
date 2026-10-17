"""Connection pool for the one PostgreSQL (decision S.1)."""

from psycopg_pool import AsyncConnectionPool

from src.config import Settings

_pool: AsyncConnectionPool | None = None


async def open_pool(settings: Settings) -> None:
    global _pool
    _pool = AsyncConnectionPool(
        settings.database_url, max_size=settings.db_pool_max_size, open=False
    )
    await _pool.open(wait=False)


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool is not open")
    return _pool
