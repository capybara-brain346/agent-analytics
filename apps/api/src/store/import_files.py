from psycopg import AsyncConnection

from src.models.domain import FilePriority


async def insert_new(
    conn: AsyncConnection, site_id: str, key: str, sha256: str, size: int, priority: FilePriority
) -> str | None:
    raise NotImplementedError


async def take_due_site(conn: AsyncConnection) -> str | None:
    raise NotImplementedError


async def files_waiting(conn: AsyncConnection) -> int:
    raise NotImplementedError
