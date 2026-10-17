from psycopg import AsyncConnection


async def generate(conn: AsyncConnection, site_id: str, window: str) -> str:
    raise NotImplementedError
