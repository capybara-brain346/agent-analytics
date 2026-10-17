"""Flow 4 · Activity reconstruction: sessions and group-bys, in one transaction for one site."""

from psycopg import AsyncConnection


async def update_views(conn: AsyncConnection, site_id: str) -> dict:
    raise NotImplementedError
