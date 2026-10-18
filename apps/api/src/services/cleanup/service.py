from datetime import UTC, datetime, timedelta

from psycopg import AsyncConnection

from src.config import get_settings
from src.logger import get_logger
from src.store import db, events, import_files
from src.store.inbox import Inbox, get_inbox

log = get_logger(__name__)


async def _delete_files(
    conn: AsyncConnection, inbox: Inbox, retention_days: int, now: datetime | None
) -> int:
    deleted = 0
    for file in await import_files.expired_success_files(conn, retention_days, now):
        try:
            await inbox.delete(file["object_key"])
        except Exception as exc:
            # The file stays marked as present; the next daily run tries again.
            log.warning(
                "raw file delete failed",
                extra={"file_id": str(file["id"]), "error": repr(exc)},
            )
            continue
        await import_files.mark_deleted(conn, file["id"])
        deleted += 1
    return deleted


async def delete_expired_raw_files(
    conn: AsyncConnection | None = None,
    inbox: Inbox | None = None,
    retention_days: int | None = None,
    now: datetime | None = None,
) -> int:
    settings = get_settings()
    inbox = inbox or get_inbox()
    days = settings.raw_retention_days if retention_days is None else retention_days
    if conn is not None:
        return await _delete_files(conn, inbox, days, now)
    async with db.connection() as own:
        return await _delete_files(own, inbox, days, now)


async def drop_expired_partitions(keep_days: int | None = None) -> int:
    # Runs on its own autocommit connection: DETACH ... CONCURRENTLY cannot run in a transaction.
    days = get_settings().events_retention_days if keep_days is None else keep_days
    return await events.drop_old_partitions(days)


PARTITION_DAYS_AHEAD = 3


async def _precreate_partitions(conn: AsyncConnection | None, now: datetime | None) -> None:
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    days = [today + timedelta(days=i) for i in range(PARTITION_DAYS_AHEAD + 1)]
    if conn is not None:
        await events.ensure_partitions(conn, days)
    else:
        async with db.connection() as own:
            await events.ensure_partitions(own, days)


async def run_cleanup(
    conn: AsyncConnection | None = None, inbox: Inbox | None = None, now: datetime | None = None
) -> dict:
    result = {
        "files_deleted": await delete_expired_raw_files(conn, inbox, now=now),
        "partitions_dropped": await drop_expired_partitions(),
    }
    # Marks older than the raw retention belong to objects the reader skips by age anyway.
    days = get_settings().raw_retention_days
    if conn is not None:
        await import_files.prune_bucket_marks(conn, days)
    else:
        async with db.connection() as own:
            await import_files.prune_bucket_marks(own, days)
    # Partitions for today and the next days exist before the import needs them (no DDL lock in
    # the import transaction).
    await _precreate_partitions(conn, now)
    return result
