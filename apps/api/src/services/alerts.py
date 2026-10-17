"""Alerts: no data for 1 h from a source (1.4), 3 failed runs in a row (7.6)."""

from psycopg import AsyncConnection


async def check_no_data(conn: AsyncConnection) -> None:
    raise NotImplementedError


async def check_failed_runs(conn: AsyncConnection, site_id: str) -> None:
    raise NotImplementedError
