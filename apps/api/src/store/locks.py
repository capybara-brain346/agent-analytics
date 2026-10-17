from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection

from src.models.domain import Lane


@asynccontextmanager
async def site_lane_lock(conn: AsyncConnection, site_id: str, lane: Lane) -> AsyncIterator[bool]:
    raise NotImplementedError
    yield False
