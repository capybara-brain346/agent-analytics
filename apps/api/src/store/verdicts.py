"""`verdicts` table: append-only, never upsert (decisions 2.8, 3.4)."""

from psycopg import AsyncConnection


async def current_verdict(conn: AsyncConnection, site_id: str, client_key: str) -> dict | None:
    raise NotImplementedError


async def append_verdict(conn: AsyncConnection, row: dict) -> int:
    raise NotImplementedError


async def verdicts_without_class(conn: AsyncConnection, site_id: str) -> list[dict]:
    raise NotImplementedError
