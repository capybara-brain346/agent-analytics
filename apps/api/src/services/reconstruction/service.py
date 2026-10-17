from psycopg import AsyncConnection


async def update_views(conn: AsyncConnection, site_id: str) -> dict:
    raise NotImplementedError
