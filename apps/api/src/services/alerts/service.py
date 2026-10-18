from datetime import datetime, timedelta

from psycopg import AsyncConnection

from src.config import get_settings
from src.logger import get_logger
from src.models.domain import AlertKind, Lane
from src.services.site_config import list_sites, load_site_config
from src.store import alerts, import_files, runs

log = get_logger(__name__)


async def check_no_data(conn: AsyncConnection, now: datetime) -> None:
    # Only live files count: a backfill upload must not hide a sender that stopped (1.4, 1.18).
    # A source that never sent a file has no baseline, so it raises no alert.
    for site_id in list_sites():
        cfg = load_site_config(site_id)
        limit = timedelta(minutes=cfg.no_data_alert_minutes)
        last = await import_files.last_received_by_source(conn, site_id, live_only=True)
        for source, seen in last.items():
            if now - seen["last_file_at"] > limit:
                message = (
                    f"No new logs from the {source} source of {site_id}"
                    f" for {cfg.no_data_alert_minutes} minutes"
                    f" (last file at {seen['last_file_at'].isoformat()})"
                )
                if await alerts.raise_alert(conn, site_id, AlertKind.NO_DATA, source, message):
                    log.warning("alert raised", extra={"site_id": site_id, "source": source})
            elif await alerts.resolve_alert(conn, site_id, AlertKind.NO_DATA, source):
                log.info("alert resolved", extra={"site_id": site_id, "source": source})


async def check_failed_runs(conn: AsyncConnection, site_id: str) -> None:
    threshold = get_settings().failed_runs_alert
    failing = []
    for lane in Lane:
        count = await runs.consecutive_failures(conn, site_id, lane)
        if count >= threshold:
            failing.append((lane, count))
    if not failing:
        if await alerts.resolve_alert(conn, site_id, AlertKind.FAILED_RUNS, None):
            log.info("alert resolved", extra={"site_id": site_id, "kind": "failed_runs"})
        return
    parts = ", ".join(f"{lane.value} lane: {count} failed runs in a row" for lane, count in failing)
    if await alerts.raise_alert(
        conn, site_id, AlertKind.FAILED_RUNS, None, f"Pipeline of {site_id} is failing ({parts})"
    ):
        log.warning("alert raised", extra={"site_id": site_id, "kind": "failed_runs"})
