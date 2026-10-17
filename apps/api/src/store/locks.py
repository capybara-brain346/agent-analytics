import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection

from src.models.domain import Lane


def lock_key(site_id: str, lane: Lane) -> int:
    digest = hashlib.sha256(f"{site_id}:{Lane(lane).value}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@asynccontextmanager
async def site_lane_lock(conn: AsyncConnection, site_id: str, lane: Lane) -> AsyncIterator[bool]:
    # Session-level lock (L1): it survives commits and ends with the connection or the unlock.
    key = lock_key(site_id, lane)
    cur = await conn.execute("select pg_try_advisory_lock(%s)", [key])
    got = (await cur.fetchone())[0]
    try:
        yield got
    finally:
        if got:
            await conn.execute("select pg_advisory_unlock(%s)", [key])


def bucket_lock_key(site_id: str, bucket: str, prefix: str) -> int:
    digest = hashlib.sha256(f"bucket:{site_id}:{bucket}:{prefix}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


@asynccontextmanager
async def advisory_lock(conn: AsyncConnection, key: int) -> AsyncIterator[bool]:
    # Session-level, like site_lane_lock: commits on the connection do not release it.
    cur = await conn.execute("select pg_try_advisory_lock(%s)", [key])
    got = (await cur.fetchone())[0]
    try:
        yield got
    finally:
        if got:
            await conn.execute("select pg_advisory_unlock(%s)", [key])
