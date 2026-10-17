"""Flow 2 · Verify identity of each client_key = (UA, client IP)."""

from psycopg import AsyncConnection


async def verify_new_clients(conn: AsyncConnection, site_id: str) -> dict:
    """Client keys with no current verdict → reuse or append a verdict row (2.8, 2.8a)."""
    raise NotImplementedError


async def reverse_dns_check(ip: str, suffixes: list[str]) -> str:
    """PTR + forward A match. Error or timeout = UNVERIFIED (decision 2.6)."""
    raise NotImplementedError
