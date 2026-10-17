from psycopg import AsyncConnection


async def check_no_data(conn: AsyncConnection) -> None:
    raise NotImplementedError


async def check_failed_runs(conn: AsyncConnection, site_id: str) -> None:
    raise NotImplementedError
