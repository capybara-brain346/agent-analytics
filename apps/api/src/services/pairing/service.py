from psycopg import AsyncConnection


async def pair_events(conn: AsyncConnection, site_id: str) -> dict:
    raise NotImplementedError
