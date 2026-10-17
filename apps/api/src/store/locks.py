"""Site + lane lock, Postgres advisory lock (L1, decision 7.2)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection

from src.models.domain import Lane


@asynccontextmanager
async def site_lane_lock(conn: AsyncConnection, site_id: str, lane: Lane) -> AsyncIterator[bool]:
    """Yield True when the lock is taken. False = another run holds it: skip this tick."""
    raise NotImplementedError
    yield False
