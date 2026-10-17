from psycopg import AsyncConnection


async def save_run(conn: AsyncConnection, site_id: str, window: str, items: list[dict]) -> str:
    raise NotImplementedError


async def cached_text(conn: AsyncConnection, bundle_hash: str) -> dict | None:
    raise NotImplementedError
