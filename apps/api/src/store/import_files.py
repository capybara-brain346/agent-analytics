"""`import_files` table: the work queue (decisions 1.18, 7.8, S.6)."""

from psycopg import AsyncConnection

from src.models.domain import FilePriority


async def insert_new(
    conn: AsyncConnection, site_id: str, key: str, sha256: str, size: int, priority: FilePriority
) -> str | None:
    """Insert with status new. Return None when sha256 already exists (unique constraint)."""
    raise NotImplementedError


async def take_due_site(conn: AsyncConnection) -> str | None:
    """Site with due work that waited longest. FOR UPDATE SKIP LOCKED (decision 7.9)."""
    raise NotImplementedError


async def files_waiting(conn: AsyncConnection) -> int:
    """Count of files with status new. Drives worker scaling."""
    raise NotImplementedError
