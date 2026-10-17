from pathlib import Path

from psycopg import AsyncConnection


async def import_due_files(conn: AsyncConnection, site_id: str) -> dict:
    raise NotImplementedError


async def import_local_file(path: Path, site_id: str, *, now: bool, force: bool) -> None:
    raise NotImplementedError
