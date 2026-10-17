"""Flow 1b · Pair CDN + origin events on edge_request_id + method + path ± N s."""

from psycopg import AsyncConnection


async def pair_events(conn: AsyncConnection, site_id: str) -> dict:
    raise NotImplementedError
