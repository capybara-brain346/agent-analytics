from psycopg import AsyncConnection


async def verify_new_clients(conn: AsyncConnection, site_id: str) -> dict:
    raise NotImplementedError


async def reverse_dns_check(ip: str, suffixes: list[str]) -> str:
    raise NotImplementedError
