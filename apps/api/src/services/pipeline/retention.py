from datetime import UTC, datetime, timedelta

from psycopg import AsyncConnection

from src.config import get_settings
from src.logger import get_logger
from src.store import db, retention

log = get_logger(__name__)


async def prune_derived(
    conn: AsyncConnection, days: int, now: datetime | None = None
) -> dict[str, int]:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
    return await retention.prune_older_than(conn, cutoff)


async def run_retention() -> dict[str, int]:
    # Daily job: derived rows live as long as the raw events they come from.
    async with db.connection() as conn:
        counts = await prune_derived(conn, get_settings().events_retention_days)
    log.info("derived retention", extra={"counts": counts})
    return counts
