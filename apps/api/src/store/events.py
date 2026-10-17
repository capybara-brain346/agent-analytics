"""`events` table, partitioned by day (decision S.2). Bulk writes with COPY."""

from collections.abc import Iterable

from psycopg import AsyncConnection


async def copy_events(conn: AsyncConnection, rows: Iterable[tuple]) -> int:
    raise NotImplementedError


async def unpaired_events(conn: AsyncConnection, site_id: str) -> list[tuple]:
    raise NotImplementedError


async def client_keys_without_verdict(conn: AsyncConnection, site_id: str) -> list[tuple]:
    raise NotImplementedError
