"""Insert test rows with plain SQL. Every `make_*` takes column overrides as keyword arguments,
returns the inserted row as a dict (all columns), and uses realistic defaults.

Default scene: GPTBot (UA `GPTBOT_UA`) at 20.171.1.5 fetches /pricing at `NOW`, status 200.
"""

import itertools
import secrets
from datetime import UTC, datetime, timedelta

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.models.keys import client_key as make_client_key

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
GPTBOT_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)"
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)
GPTBOT_IP = "20.171.1.5"

JSON_COLUMNS = {
    "counts",
    "evidence",
    "bundle",
    "text",
    "factor_reasons",
    "status_counts",
    "journeys_reached",
}
_counter = itertools.count(1)


def _n() -> int:
    return next(_counter)


async def insert_row(conn: AsyncConnection, table: str, values: dict) -> dict:
    values = {k: Jsonb(v) if k in JSON_COLUMNS and v is not None else v for k, v in values.items()}
    columns = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"insert into {table} ({columns}) values ({marks}) returning *", list(values.values())
        )
        return await cur.fetchone()


async def make_import_file(conn: AsyncConnection, **o) -> dict:
    n = _n()
    values = {
        "site_id": "example",
        "source": "origin",
        "object_key": f"inbox/example/file-{n}.gz",
        "sha256": secrets.token_hex(32),
        "size_bytes": 1000,
        "priority": "live",
        "status": "new",
        "received_at": NOW,
    } | o
    return await insert_row(conn, "import_files", values)


async def make_event(conn: AsyncConnection, **o) -> dict:
    n = _n()
    ts = o.get("ts", NOW)
    values = {
        "site_id": "example",
        "ts": ts,
        "source": "origin",
        "method": "GET",
        "path": "/pricing",
        "status": 200,
        "bytes_sent": 5120,
        "client_ip": GPTBOT_IP,
        "user_agent": GPTBOT_UA,
        "request_id": None,
        "edge_request_id": None,
        "edge_signal": "none",
        "line_key": f"line-{n}",
        "pair_state": "single",
        "cdn_bypass": False,
        "verdict_id": None,
        "file_id": None,
        "imported_at": ts,
    } | o
    if "client_key" not in o:
        values["client_key"] = make_client_key(values["user_agent"], values["client_ip"])
    await conn.execute("select ensure_events_partition(%s)", [ts.astimezone(UTC).date()])
    return await insert_row(conn, "events", values)


async def make_verdict(conn: AsyncConnection, *, classified: bool = False, **o) -> dict:
    ua = o.get("user_agent", GPTBOT_UA)
    ip = o.get("client_ip", GPTBOT_IP)
    values = {
        "site_id": "example",
        "client_key": make_client_key(ua, ip),
        "edge_signal": "none",
        "user_agent": ua,
        "client_ip": ip,
        "claimed_agent": "gptbot",
        "registry_category": "ai_crawler",
        "verdict": "VERIFIED",
        "method": "ip_list",
        "evidence": "in vendor list, snapshot 2026-10-10",
        "registry_version": "1",
        "ip_snapshot_version": "2026-10-10",
        "checked_at": NOW,
    }
    if classified:
        values |= {
            "traffic_class": 2,
            "confidence": "high",
            "rule_id": "R3",
            "rule_version": "1",
            "class_evidence": "AI crawler, verified",
            "ua_type": "bot",
            "classified_at": NOW,
        }
    return await insert_row(conn, "verdicts", values | o)


_SESSION_DEFAULTS = {
    "site_id": "example",
    "version": 1,
    "claimed_agent": "gptbot",
    "traffic_class": 2,
    "confidence": "high",
    "requests": 3,
    "distinct_pages": 3,
    "pages_in_order": ["/pricing", "/products", "/docs/api"],
    "key_pages_visited": 3,
    "reached_conversion": False,
    "has_retry": False,
    "has_loop": False,
    "retries": 0,
    "shared_ip": False,
    "gaps": [],
}


async def make_session(conn: AsyncConnection, *, open: bool = False, **o) -> dict:
    n = _n()
    values = (
        _SESSION_DEFAULTS
        | {
            "session_id": f"s-{n}",
            "client_key": make_client_key(GPTBOT_UA, GPTBOT_IP),
            "user_agent": GPTBOT_UA,
            "client_ip": GPTBOT_IP,
            "started": NOW - timedelta(minutes=5),
            "last_seen": NOW,
        }
        | o
    )
    return await insert_row(conn, "open_sessions" if open else "sessions", values)


async def make_session_event(conn: AsyncConnection, **o) -> dict:
    n = _n()
    values = {
        "site_id": "example",
        "session_id": "s-1",
        "event_id": n,
        "event_ts": NOW,
        "seq": n,
    } | o
    return await insert_row(conn, "session_events", values)


async def make_page_stats(conn: AsyncConnection, **o) -> dict:
    values = {
        "site_id": "example",
        "hour": NOW.replace(minute=0),
        "path": "/pricing",
        "traffic_class": 2,
        "tags": ["key"],
        "requests": 10,
        "sessions": 4,
        "clients": 2,
        "median_bytes": 5120,
        "n_2xx": 10,
    } | o
    return await insert_row(conn, "page_stats", values)


async def make_journey_step(conn: AsyncConnection, **o) -> dict:
    values = {
        "site_id": "example",
        "hour": NOW.replace(minute=0),
        "journey_id": "signup",
        "traffic_class": 2,
        "step_no": 1,
        "step_path": "/pricing",
        "sessions_reached": 10,
        "sessions_retry_or_loop": 0,
    } | o
    return await insert_row(conn, "journey_steps", values)


async def make_agent(conn: AsyncConnection, **o) -> dict:
    values = {
        "site_id": "example",
        "hour": NOW.replace(minute=0),
        "claimed_agent": "gptbot",
        "traffic_class": 2,
        "verification": "VERIFIED",
        "confidence": "high",
        "first_seen": NOW - timedelta(minutes=5),
        "last_seen": NOW,
        "requests": 10,
        "sessions": 2,
        "distinct_pages": 3,
        "top_paths": ["/pricing", "/products"],
    } | o
    return await insert_row(conn, "agents", values)


async def make_recommendation_run(conn: AsyncConnection, **o) -> dict:
    values = {
        "site_id": "example",
        "window_size": "6h",
        "window_start": NOW - timedelta(hours=6),
        "window_end": NOW,
        "rule_version": "1",
        "prompt_version": "1",
        "model": "claude-sonnet-5-5",
        "status": "success",
        "started_at": NOW,
        "finished_at": NOW,
    } | o
    return await insert_row(conn, "recommendation_runs", values)


async def make_recommendation(conn: AsyncConnection, **o) -> dict:
    if "run_id" not in o:
        o["run_id"] = (await make_recommendation_run(conn, site_id=o.get("site_id", "example")))[
            "id"
        ]
    values = {
        "site_id": "example",
        "stable_id": "p2-pricing",
        "rank": 1,
        "pattern": "P2",
        "target": "/pricing",
        "score": 18,
        "impact": 3,
        "frequency": 2,
        "severity": 3,
        "confidence_factor": 1.0,
        "confidence": "high",
        "recommended_test": "Agent fetch of /pricing",
        "reason": "AI crawlers get 403 on /pricing.",
        "evidence": {"sessions": ["s-1"], "events": [1]},
        "sessions_count": 1,
        "events_count": 1,
        "text_source": "template",
        "change": "new",
        "bundle": {},
    } | o
    return await insert_row(conn, "recommendations", values)


async def make_pipeline_run(conn: AsyncConnection, **o) -> dict:
    values = {
        "site_id": "example",
        "lane": "fast",
        "started_at": NOW,
        "finished_at": NOW,
        "status": "success",
        "counts": {},
    } | o
    return await insert_row(conn, "pipeline_runs", values)


async def make_site_work(conn: AsyncConnection, **o) -> dict:
    values = {"site_id": "example", "lane": "fast"} | o
    return await insert_row(conn, "site_work", values)


async def make_alert(conn: AsyncConnection, **o) -> dict:
    values = {
        "site_id": "example",
        "kind": "no_data",
        "source": "cdn",
        "message": "No new logs from the CDN for 60 minutes",
        "raised_at": NOW,
    } | o
    return await insert_row(conn, "alerts", values)


async def make_ip_list_snapshot(conn: AsyncConnection, **o) -> dict:
    values = {
        "source": "openai-gptbot.json",
        "version": "2026-10-10",
        "fetched_at": NOW,
        "prefixes": ["20.171.0.0/16"],
    } | o
    return await insert_row(conn, "ip_list_snapshots", values)
