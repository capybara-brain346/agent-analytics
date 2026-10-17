from psycopg import AsyncConnection


async def update_open_sessions(conn: AsyncConnection, site_id: str) -> None:
    raise NotImplementedError


async def close_idle_sessions(conn: AsyncConnection, site_id: str) -> None:
    raise NotImplementedError


async def update_current_hour(conn: AsyncConnection, site_id: str) -> None:
    raise NotImplementedError


async def recompute_range(conn: AsyncConnection, site_id: str, client_key: str) -> None:
    raise NotImplementedError
