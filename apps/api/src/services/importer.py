"""Flow 1 · Import logs: inbox file → parse · validate · dedupe → events."""

from pathlib import Path

from psycopg import AsyncConnection


async def import_due_files(conn: AsyncConnection, site_id: str) -> dict:
    """Import files with status new for one site, live before backfill, within the work limit."""
    raise NotImplementedError


async def import_local_file(path: Path, site_id: str, *, now: bool, force: bool) -> None:
    """CLI entry: put a file into the inbox as backfill; with `now`, import at once."""
    raise NotImplementedError
