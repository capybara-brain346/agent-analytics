from datetime import UTC, datetime, timedelta

from psycopg import AsyncConnection

from src.config import get_settings
from src.services import site_config
from src.store import pairing as store


async def pair_events(conn: AsyncConnection, site_id: str, now: datetime | None = None) -> dict:
    counts = {"paired": 0, "single": 0, "cdn_bypass": 0}
    if not site_config.load_site_config(site_id).pairs_sources:
        return counts
    settings = get_settings()
    now = now or datetime.now(UTC)
    counts["paired"] = await store.pair_pending(conn, site_id, settings.pair_window_seconds)
    # A row without edge_request_id cannot pair (1b.7). It is not made single at once: it waits
    # like the others, so one rule covers all rows. After the wait it is single; an origin row
    # then also gets cdn_bypass.
    cutoff = now - timedelta(minutes=settings.pair_wait_minutes)
    hard_cutoff = now - timedelta(hours=settings.pair_hard_limit_hours)
    counts["single"], counts["cdn_bypass"] = await store.expire_pending(
        conn, site_id, cutoff, hard_cutoff
    )
    return counts
