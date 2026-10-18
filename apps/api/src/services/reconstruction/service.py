from datetime import UTC, datetime

from psycopg import AsyncConnection

from src.config import get_settings
from src.models.domain import SourceType
from src.services import registry, site_config
from src.store import views


async def update_views(conn: AsyncConnection, site_id: str, now: datetime | None = None) -> dict:
    settings = get_settings()
    config = site_config.load_site_config(site_id)
    now = now or datetime.now(UTC)
    journeys = [(j.id, n, path) for j in config.journeys for n, path in enumerate(j.steps, 1)]
    params = {
        "now": now,
        "gap": settings.session_gap_minutes,
        "agent_gap": settings.agent_session_gap_minutes,
        "margin": settings.delivery_margin_minutes,
        "retry": settings.retry_window_seconds,
        "loop": settings.loop_repeat_count,
        "key": config.key_pages,
        "conv": config.conversion_pages,
        "jid": [j[0] for j in journeys],
        "jno": [j[1] for j in journeys],
        "jpath": [j[2] for j in journeys],
    }
    base_gaps = ["outcome unknown"]
    if SourceType.CDN not in config.sources:
        base_gaps.insert(0, "no CDN log: edge blocks unknown")

    counts = {
        "clients_recomputed": 0,
        "sessions_written": 0,
        "sessions_open": 0,
        "sessions_closed": 0,
        "sessions_recomputed_closed": 0,
        "hours_updated": 0,
    }
    async with conn.transaction():
        gap_max = max(settings.session_gap_minutes, settings.agent_session_gap_minutes)
        staged = await views.stage_new_events(conn, site_id, now, gap_max)
        counts["clients_recomputed"] = staged["clients"]
        if staged["clients"]:
            built = await views.stage_sessions(conn, site_id, params)
            shared = [ip for ip in await views.session_ips(conn) if registry.is_shared_ip(ip)]
            written = await views.finish_sessions(conn, site_id, params, shared, base_gaps)
            counts["sessions_written"] = built
            counts["sessions_open"] = written["open"]
            counts["sessions_closed"] = written["closed"]
            counts["sessions_recomputed_closed"] = written["recomputed_closed"]
        counts["sessions_closed"] += await views.close_idle_sessions(
            conn, site_id, now, params["gap"], params["agent_gap"], params["margin"]
        )
        counts["hours_updated"] = await views.refresh_hours(conn, site_id, params)
        counts["events_flagged"] = await views.mark_in_views(conn, site_id)
    return counts
