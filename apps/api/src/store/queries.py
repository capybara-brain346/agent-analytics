import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from psycopg import AsyncConnection
from psycopg.rows import dict_row

STATUS_TOKEN = re.compile(r"^([1-5])(\d\d|xx)$")

# Closed and still-open visits as one set; `in_progress` marks the open ones (decision 7.7).
SESSIONS_UNION = """(
    select s.*, false as in_progress from sessions s
    union all
    select o.*, true as in_progress from open_sessions o
)"""


@dataclass(frozen=True)
class Filters:
    site_id: str
    start: datetime
    end: datetime
    classes: list[int] = field(default_factory=list)
    agent: str | None = None
    verdict: str | None = None
    verdict_id: int | None = None
    confidence: str | None = None
    status: str | None = None  # "403", "4xx", or a comma list "403,429"
    path_contains: str | None = None
    client_key: str | None = None
    session_id: str | None = None
    source: str | None = None
    file_id: str | None = None


def valid_status(value: str) -> bool:
    return all(STATUS_TOKEN.match(t.strip()) for t in value.split(","))


def _status_sql(value: str, col: str = "e.status") -> tuple[str, list]:
    parts, params = [], []
    for token in value.split(","):
        m = STATUS_TOKEN.match(token.strip())
        if m is None:
            continue
        if m.group(2) == "xx":
            lo = int(m.group(1)) * 100
            parts.append(f"({col} between %s and %s)")
            params += [lo, lo + 99]
        else:
            parts.append(f"{col} = %s")
            params.append(int(token))
    return "(" + " or ".join(parts or ["false"]) + ")", params


def _event_where(f: Filters) -> tuple[str, list]:
    # Events join their verdict row (class, agent, verdict). Pending pairs are never shown.
    conds = ["e.site_id = %s", "e.ts >= %s", "e.ts < %s", "e.pair_state <> 'pending'"]
    params: list = [f.site_id, f.start, f.end]
    if f.classes:
        conds.append("v.traffic_class = any(%s)")
        params.append(f.classes)
    if f.agent:
        conds.append("v.claimed_agent = %s")
        params.append(f.agent)
    if f.verdict:
        conds.append("v.verdict = %s")
        params.append(f.verdict)
    if f.verdict_id is not None:
        conds.append("e.verdict_id = %s")
        params.append(f.verdict_id)
    if f.confidence:
        conds.append("v.confidence = %s")
        params.append(f.confidence)
    if f.status:
        sql, p = _status_sql(f.status)
        conds.append(sql)
        params += p
    if f.path_contains:
        conds.append("position(lower(%s) in lower(e.path)) > 0")
        params.append(f.path_contains)
    if f.client_key:
        conds.append("e.client_key = %s")
        params.append(f.client_key)
    if f.session_id:
        conds.append(
            "exists (select 1 from session_events se where se.site_id = e.site_id"
            " and se.event_id = e.id and se.session_id = %s)"
        )
        params.append(f.session_id)
    if f.source:
        conds.append("e.source = %s")
        params.append(f.source)
    if f.file_id:
        conds.append("e.file_id = %s::uuid")
        params.append(f.file_id)
    return " and ".join(conds), params


EVENT_FROM = "events e left join verdicts v on v.id = e.verdict_id"


async def _all(conn: AsyncConnection, sql: str, params: list | tuple = ()) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchall()


async def _one(conn: AsyncConnection, sql: str, params: list | tuple = ()) -> dict | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        return await cur.fetchone()


# ---------------------------------------------------------------- overview


async def overview_numbers(conn: AsyncConnection, f: Filters) -> dict:
    where, params = _event_where(f)
    row = await _one(
        conn,
        f"""
        select count(*) as total,
               count(*) filter (where v.traffic_class between 1 and 4) as agent_requests,
               count(distinct v.claimed_agent)
                   filter (where v.traffic_class between 1 and 4) as distinct_agents,
               count(*) filter (where e.status >= 400) as errors,
               count(*) filter (where e.status in (403, 429)) as denied
        from {EVENT_FROM} where {where}
        """,
        params,
    )
    return row or {}


async def traffic_by_class_confidence(conn: AsyncConnection, f: Filters) -> list[dict]:
    where, params = _event_where(f)
    return await _all(
        conn,
        f"""
        select v.traffic_class, v.confidence, count(*) as requests
        from {EVENT_FROM} where {where}
        group by 1, 2
        """,
        params,
    )


async def trend(conn: AsyncConnection, f: Filters, bucket: str = "hour") -> list[dict]:
    unit = "day" if bucket == "day" else "hour"
    where, params = _event_where(f)
    return await _all(
        conn,
        f"""
        select date_trunc('{unit}', e.ts, 'UTC') as bucket, v.traffic_class, count(*) as requests
        from {EVENT_FROM} where {where}
        group by 1, 2 order by 1, 2
        """,
        params,
    )


async def top_agents(conn: AsyncConnection, f: Filters, limit: int) -> list[dict]:
    where, params = _event_where(f)
    return await _all(
        conn,
        f"""
        select v.claimed_agent as agent, v.traffic_class, count(*) as requests
        from {EVENT_FROM}
        where {where} and v.traffic_class between 1 and 4 and v.claimed_agent is not null
        group by 1, 2 order by requests desc, agent limit %s
        """,
        [*params, limit],
    )


async def top_pages(conn: AsyncConnection, f: Filters, limit: int) -> list[dict]:
    where, params = _event_where(f)
    return await _all(
        conn,
        f"""
        select e.path, count(*) as agent_requests,
               count(*) filter (where e.status >= 400) as errors,
               count(*) filter (where e.status in (403, 429)) as blocks
        from {EVENT_FROM}
        where {where} and v.traffic_class between 1 and 4
        group by 1 order by agent_requests desc, e.path limit %s
        """,
        [*params, limit],
    )


async def source_counts(conn: AsyncConnection, f: Filters) -> dict[str, int]:
    where, params = _event_where(f)
    rows = await _all(
        conn, f"select e.source, count(*) as n from {EVENT_FROM} where {where} group by 1", params
    )
    return {r["source"]: r["n"] for r in rows}


async def freshness(conn: AsyncConnection, site_id: str) -> dict:
    last_success = await _one(
        conn,
        "select max(finished_at) as at from pipeline_runs"
        " where site_id = %s and lane = 'fast' and status = 'success'",
        [site_id],
    )
    latest = await _one(
        conn,
        """
        select id::text as id, status, failed_step, started_at, finished_at
        from pipeline_runs where site_id = %s and lane = 'fast'
        order by started_at desc limit 1
        """,
        [site_id],
    )
    work = await _one(
        conn,
        "select consecutive_failures, last_success_at from site_work"
        " where site_id = %s and lane = 'fast'",
        [site_id],
    )
    imports = await _one(
        conn,
        "select max(finished_at) as at from import_files where site_id = %s and status = 'success'",
        [site_id],
    )
    return {
        "data_up_to": (last_success or {}).get("at") or (work or {}).get("last_success_at"),
        "latest_run": latest,
        "consecutive_failures": (work or {}).get("consecutive_failures", 0),
        "last_import_at": (imports or {}).get("at"),
    }


async def open_alerts(conn: AsyncConnection, site_id: str) -> list[dict]:
    return await _all(
        conn,
        """
        select id, kind, source, message, raised_at, resolved_at from alerts
        where site_id = %s and resolved_at is null order by raised_at desc, id desc
        """,
        [site_id],
    )


# ---------------------------------------------------------------- events

EVENT_LIST_COLUMNS = """
    e.id, e.ts, e.method, e.host, e.path, e.status, e.edge_status, e.origin_status,
    e.source, e.pair_state, e.client_key, e.user_agent, host(e.client_ip) as client_ip,
    e.verdict_id, v.claimed_agent, v.verdict, v.confidence, v.traffic_class,
    (select se.session_id from session_events se
      where se.site_id = e.site_id and se.event_id = e.id limit 1) as session_id
"""


async def list_events(
    conn: AsyncConnection, f: Filters, limit: int, offset: int
) -> tuple[list[dict], int]:
    where, params = _event_where(f)
    rows = await _all(
        conn,
        f"""
        select {EVENT_LIST_COLUMNS} from {EVENT_FROM} where {where}
        order by e.ts desc, e.id desc limit %s offset %s
        """,
        [*params, limit, offset],
    )
    total = await _one(conn, f"select count(*) as n from {EVENT_FROM} where {where}", params)
    return rows, total["n"]


async def get_event(conn: AsyncConnection, site_id: str, event_id: int) -> dict | None:
    event = await _one(
        conn,
        """
        select e.id, e.ts, e.method, e.host, e.path, e.status, e.edge_status, e.origin_status,
               e.bytes_sent, e.response_time_ms, e.referrer, e.user_agent,
               host(e.client_ip) as client_ip, e.client_key, e.request_id, e.edge_request_id,
               e.edge_signal, e.source, e.pair_state, e.cdn_bypass, e.verdict_id,
               e.file_id::text as file_id, e.line_no
        from events e where e.site_id = %s and e.id = %s
        """,
        [site_id, event_id],
    )
    if event is None:
        return None
    event["verdict_row"] = (
        await _one(
            conn, f"select {VERDICT_COLUMNS} from verdicts v where v.id = %s", [event["verdict_id"]]
        )
        if event["verdict_id"] is not None
        else None
    )
    link = await _one(
        conn,
        """
        select se.session_id, se.seq,
               (select count(*) from session_events x
                 where x.site_id = se.site_id and x.session_id = se.session_id) as total
        from session_events se where se.site_id = %s and se.event_id = %s limit 1
        """,
        [site_id, event_id],
    )
    event["session"] = link
    event["import_file"] = (
        await _one(
            conn,
            """
            select id::text as id, source, entry, status, received_at, finished_at, lines_total,
                   lines_imported, lines_rejected, lines_duplicate, object_key
            from import_files where id = %s::uuid and site_id = %s
            """,
            [event["file_id"], site_id],
        )
        if event["file_id"]
        else None
    )
    event["recommendations"] = await _all(
        conn,
        """
        select r.id, r.run_id, r.pattern, r.target, r.score from recommendations r
        where r.site_id = %s and r.evidence -> 'events' @> to_jsonb(%s::bigint)
        order by r.run_id desc, r.id desc limit 20
        """,
        [site_id, event_id],
    )
    return event


VERDICT_COLUMNS = """
    v.id, v.client_key, v.edge_signal, v.user_agent, host(v.client_ip) as client_ip,
    v.claimed_agent, v.registry_category, v.verdict, v.method, v.evidence, v.registry_version,
    v.ip_snapshot_version, v.checked_at, v.traffic_class, v.confidence, v.rule_id,
    v.rule_version, v.class_evidence, v.flags, v.ua_type, v.classified_at
"""


# ---------------------------------------------------------------- sessions

SESSION_COLUMNS = """
    s.session_id, s.version, s.client_key, s.verdict_id, s.claimed_agent, s.user_agent,
    host(s.client_ip) as client_ip, s.edge_signal, s.traffic_class, s.confidence, s.started,
    s.last_seen, s.requests, s.distinct_pages, s.pages_in_order, s.key_pages_visited,
    s.reached_conversion, s.has_retry, s.has_loop, s.retries, s.shared_ip, s.gaps,
    s.status_counts, s.journeys_reached, s.in_progress
"""


def _session_where(
    f: Filters,
    in_progress: bool | None = None,
    has_retry: bool | None = None,
    has_loop: bool | None = None,
    reached_conversion: bool | None = None,
    journey: str | None = None,
    reached_step: int | None = None,
) -> tuple[str, list]:
    conds = ["s.site_id = %s", "s.started < %s", "s.last_seen >= %s"]
    params: list = [f.site_id, f.end, f.start]
    if f.classes:
        conds.append("s.traffic_class = any(%s)")
        params.append(f.classes)
    if f.agent:
        conds.append("s.claimed_agent = %s")
        params.append(f.agent)
    if f.confidence:
        conds.append("s.confidence = %s")
        params.append(f.confidence)
    if f.client_key:
        conds.append("s.client_key = %s")
        params.append(f.client_key)
    for col, value in (
        ("in_progress", in_progress),
        ("has_retry", has_retry),
        ("has_loop", has_loop),
        ("reached_conversion", reached_conversion),
    ):
        if value is not None:
            conds.append(f"s.{col} = %s")
            params.append(value)
    if journey:
        if reached_step:
            conds.append("coalesce((s.journeys_reached ->> %s)::int, 0) >= %s")
            params += [journey, reached_step]
        else:
            conds.append("s.journeys_reached ? %s")
            params.append(journey)
    return " and ".join(conds), params


async def list_sessions(
    conn: AsyncConnection, f: Filters, limit: int, offset: int, **extra
) -> tuple[list[dict], int]:
    where, params = _session_where(f, **extra)
    rows = await _all(
        conn,
        f"""
        select {SESSION_COLUMNS} from {SESSIONS_UNION} s where {where}
        order by s.started desc, s.session_id limit %s offset %s
        """,
        [*params, limit, offset],
    )
    total = await _one(conn, f"select count(*) as n from {SESSIONS_UNION} s where {where}", params)
    return rows, total["n"]


async def get_session(conn: AsyncConnection, site_id: str, session_id: str) -> dict | None:
    session = await _one(
        conn,
        f"select {SESSION_COLUMNS} from {SESSIONS_UNION} s"
        " where s.site_id = %s and s.session_id = %s",
        [site_id, session_id],
    )
    if session is None:
        return None
    session["events"] = await _all(
        conn,
        """
        select se.seq, e.id, e.ts, e.method, e.path, e.status, e.source, e.bytes_sent
        from session_events se
        join events e on e.site_id = se.site_id and e.ts = se.event_ts and e.id = se.event_id
        where se.site_id = %s and se.session_id = %s order by se.seq
        """,
        [site_id, session_id],
    )
    session["verdict_row"] = (
        await _one(
            conn,
            f"select {VERDICT_COLUMNS} from verdicts v where v.id = %s",
            [session["verdict_id"]],
        )
        if session["verdict_id"] is not None
        else None
    )
    session["recommendations"] = await _all(
        conn,
        """
        select r.id, r.run_id, r.pattern, r.target, r.score from recommendations r
        where r.site_id = %s and r.evidence -> 'sessions' @> to_jsonb(%s::text)
        order by r.run_id desc, r.id desc limit 20
        """,
        [site_id, session_id],
    )
    return session


# ---------------------------------------------------------------- agents


def _hour_range(f: Filters) -> tuple[str, list]:
    return "a.hour >= date_trunc('hour', %s::timestamptz, 'UTC') and a.hour < %s", [f.start, f.end]


async def list_agents(
    conn: AsyncConnection, f: Filters, verification: str | None = None, q: str | None = None
) -> list[dict]:
    hours, hp = _hour_range(f)
    conds = ["a.site_id = %s", hours]
    params: list = [f.site_id, *hp]
    if f.classes:
        conds.append("a.traffic_class = any(%s)")
        params.append(f.classes)
    if q:
        conds.append("position(lower(%s) in lower(a.claimed_agent)) > 0")
        params.append(q)
    where = " and ".join(conds)
    rows = await _all(
        conn,
        f"""
        select a.claimed_agent, a.traffic_class,
               (array_agg(a.verification order by a.hour desc))[1] as verification,
               (array_agg(a.confidence order by a.hour desc))[1] as confidence,
               min(a.first_seen) as first_seen, max(a.last_seen) as last_seen,
               sum(a.requests)::bigint as requests
        from agents a where {where}
        group by a.claimed_agent, a.traffic_class
        order by requests desc, a.claimed_agent, a.traffic_class
        """,
        params,
    )
    if verification:
        rows = [r for r in rows if r["verification"] == verification]
    if not rows:
        return rows
    # Distinct counts come from the session tables, never from adding hourly rows.
    sw, sp = _session_where(f)
    stats = await _all(
        conn,
        f"""
        select s.claimed_agent, s.traffic_class, count(*) as sessions,
               (select count(distinct p) from {SESSIONS_UNION} s2,
                       lateral unnest(s2.pages_in_order) p
                 where s2.site_id = s.site_id and s2.claimed_agent = s.claimed_agent
                   and s2.traffic_class = s.traffic_class
                   and s2.started < %s and s2.last_seen >= %s) as distinct_pages
        from {SESSIONS_UNION} s where {sw}
        group by s.site_id, s.claimed_agent, s.traffic_class
        """,
        [f.end, f.start, *sp],
    )
    by_key = {(r["claimed_agent"], r["traffic_class"]): r for r in stats}
    paths = await _all(
        conn,
        f"""
        select claimed_agent, traffic_class, path from (
            select a.claimed_agent, a.traffic_class, p.path,
                   row_number() over (
                       partition by a.claimed_agent, a.traffic_class
                       order by count(*) desc, p.path
                   ) as rn
            from agents a, lateral unnest(a.top_paths) as p(path)
            where {where}
            group by a.claimed_agent, a.traffic_class, p.path
        ) t where rn <= 3 order by claimed_agent, traffic_class, rn
        """,
        params,
    )
    common: dict[tuple, list[str]] = {}
    for r in paths:
        common.setdefault((r["claimed_agent"], r["traffic_class"]), []).append(r["path"])
    for r in rows:
        key = (r["claimed_agent"], r["traffic_class"])
        r["sessions"] = by_key.get(key, {}).get("sessions", 0)
        r["distinct_pages"] = by_key.get(key, {}).get("distinct_pages", 0)
        r["common_paths"] = common.get(key, [])
    return rows


async def get_agent(conn: AsyncConnection, f: Filters, agent_id: str) -> dict | None:
    exists = await _one(
        conn,
        "select 1 as x from agents where site_id = %s and claimed_agent = %s"
        " union all select 1 from verdicts where site_id = %s and claimed_agent = %s limit 1",
        [f.site_id, agent_id, f.site_id, agent_id],
    )
    if exists is None:
        return None
    hours, hp = _hour_range(f)
    latest = await _one(
        conn,
        """
        select traffic_class, verification, confidence, first_seen, last_seen
        from agents a where a.site_id = %s and a.claimed_agent = %s
        order by a.hour desc limit 1
        """,
        [f.site_id, agent_id],
    )
    history = await _all(
        conn,
        f"""
        select {VERDICT_COLUMNS},
               exists (select 1 from sessions s where s.site_id = v.site_id
                        and s.client_key = v.client_key and s.shared_ip) as shared_ip
        from verdicts v where v.site_id = %s and v.claimed_agent = %s
        order by v.id desc limit 100
        """,
        [f.site_id, agent_id],
    )
    activity = await _all(
        conn,
        f"""
        select a.hour, sum(a.requests)::bigint as requests from agents a
        where a.site_id = %s and a.claimed_agent = %s and {hours}
        group by a.hour order by a.hour
        """,
        [f.site_id, agent_id, *hp],
    )
    ef = Filters(f.site_id, f.start, f.end, agent=agent_id)
    where, params = _event_where(ef)
    top_paths = await _all(
        conn,
        f"""
        select e.path, count(*) as requests from {EVENT_FROM} where {where}
        group by 1 order by requests desc, e.path limit 10
        """,
        params,
    )
    status_mix = await _all(
        conn,
        f"""
        select e.status, count(*) as requests from {EVENT_FROM} where {where}
        group by 1 order by 1
        """,
        params,
    )
    sessions, _ = await list_sessions(conn, ef, 50, 0)
    return {
        "latest": latest,
        "verdict_history": history,
        "activity": activity,
        "top_paths": top_paths,
        "status_mix": status_mix,
        "sessions": sessions,
    }


# ---------------------------------------------------------------- pages


def _page_range(f: Filters) -> tuple[str, list]:
    conds = [
        "p.site_id = %s",
        "p.hour >= date_trunc('hour', %s::timestamptz, 'UTC')",
        "p.hour < %s",
    ]
    params: list = [f.site_id, f.start, f.end]
    if f.classes:
        conds.append("p.traffic_class = any(%s)")
        params.append(f.classes)
    return " and ".join(conds), params


async def list_pages(conn: AsyncConnection, f: Filters) -> list[dict]:
    where, params = _page_range(f)
    rows = await _all(
        conn,
        f"""
        select p.path, (array_agg(to_jsonb(p.tags) order by p.hour desc))[1] as tags,
               sum(p.requests)::bigint as requests,
               sum(p.requests) filter (where p.traffic_class between 1 and 4)::bigint
                   as agent_requests,
               sum(p.n_4xx + p.n_5xx)::bigint as errors,
               sum(p.n_403 + p.n_429)::bigint as blocks,
               sum(p.retries)::bigint as retries,
               percentile_disc(0.5) within group (order by p.median_bytes) as median_bytes
        from page_stats p where {where}
        group by p.path order by agent_requests desc nulls last, requests desc, p.path
        """,
        params,
    )
    sw, sp = _session_where(f)
    sessions = await _all(
        conn,
        f"""
        select pg as path, count(distinct s.session_id) as sessions,
               count(distinct s.claimed_agent) as agents
        from {SESSIONS_UNION} s, lateral unnest(s.pages_in_order) pg
        where {sw} group by pg
        """,
        sp,
    )
    by_path = {r["path"]: r for r in sessions}
    for r in rows:
        s = by_path.get(r["path"], {})
        r["sessions"] = s.get("sessions", 0)
        r["agents"] = s.get("agents", 0)
    return rows


async def get_page(conn: AsyncConnection, f: Filters, path: str) -> dict | None:
    where, params = _page_range(f)
    where += " and p.path = %s"
    params.append(path)
    by_class = await _all(
        conn,
        f"""
        select p.traffic_class, sum(p.requests)::bigint as requests,
               sum(p.n_2xx)::bigint as n_2xx, sum(p.n_3xx)::bigint as n_3xx,
               sum(p.n_403)::bigint as n_403, sum(p.n_429)::bigint as n_429,
               sum(p.n_4xx)::bigint as n_4xx, sum(p.n_5xx)::bigint as n_5xx,
               sum(p.retries)::bigint as retries
        from page_stats p where {where} group by 1 order by 1
        """,
        params,
    )
    over_time = await _all(
        conn,
        f"""
        select p.hour, sum(p.requests)::bigint as requests,
               sum(p.n_4xx + p.n_5xx)::bigint as errors
        from page_stats p where {where} group by 1 order by 1
        """,
        params,
    )
    tags_row = await _one(
        conn,
        "select tags from page_stats where site_id = %s and path = %s order by hour desc limit 1",
        [f.site_id, path],
    )
    sw, sp = _session_where(f)
    sw += " and %s = any(s.pages_in_order)"
    sp = [*sp, path]
    agents = await _all(
        conn,
        f"""
        select s.claimed_agent, s.traffic_class, count(*) as sessions
        from {SESSIONS_UNION} s where {sw}
        group by 1, 2 order by sessions desc, 1
        """,
        sp,
    )
    sessions = await _all(
        conn,
        f"""
        select {SESSION_COLUMNS} from {SESSIONS_UNION} s where {sw}
        order by s.started desc, s.session_id limit 50
        """,
        sp,
    )
    recommendations = await _all(
        conn,
        """
        select r.id, r.run_id, r.pattern, r.target, r.score, r.confidence, r.change
        from recommendations r
        where r.run_id = (select max(id) from recommendation_runs
                           where site_id = %s and status = 'success')
          and r.change is distinct from 'gone' and position(%s in r.target) > 0
        order by r.rank, r.id
        """,
        [f.site_id, path],
    )
    return {
        "tags": tags_row["tags"] if tags_row else None,
        "by_class": by_class,
        "over_time": over_time,
        "agents": agents,
        "sessions": sessions,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------- journeys


async def list_journeys(conn: AsyncConnection, f: Filters) -> list[dict]:
    # Exact funnel from sessions: highest step reached for each journey (journeys_reached).
    sw, sp = _session_where(f)
    reached = await _all(
        conn,
        f"""
        select s.traffic_class, j.key as journey_id, j.value::int as highest, count(*) as sessions
        from {SESSIONS_UNION} s, lateral jsonb_each_text(s.journeys_reached) j
        where {sw} group by 1, 2, 3
        """,
        sp,
    )
    # Retry/loop: distinct sessions that had a retry or loop at the step (retry_paths). The hourly
    # rows only list the steps; adding them would count a long session once for each hour.
    where, params = _page_range(f)
    where = where.replace("p.", "j.")
    retry = await _all(
        conn,
        f"""
        select st.journey_id, st.traffic_class, st.step_no,
               count(distinct s.session_id) as retry_or_loop
        from (
            select distinct j.journey_id, j.traffic_class, j.step_no, j.step_path
            from journey_steps j where {where}
        ) st
        join {SESSIONS_UNION} s
          on s.traffic_class = st.traffic_class and s.retry_paths @> array[st.step_path]
         and jsonb_exists(s.journeys_reached, st.journey_id)
        where {sw}
        group by 1, 2, 3
        """,
        [*params, *sp],
    )
    return [{"kind": "reached", **r} for r in reached] + [{"kind": "retry", **r} for r in retry]


# ---------------------------------------------------------------- recommendations


async def latest_run(conn: AsyncConnection, site_id: str, run_id: int | None = None) -> dict | None:
    if run_id is not None:
        return await _one(
            conn,
            "select * from recommendation_runs where site_id = %s and id = %s",
            [site_id, run_id],
        )
    return await _one(
        conn,
        "select * from recommendation_runs where site_id = %s and status = 'success'"
        " order by id desc limit 1",
        [site_id],
    )


async def previous_run_id(conn: AsyncConnection, site_id: str, run_id: int) -> int | None:
    row = await _one(
        conn,
        "select max(id) as id from recommendation_runs"
        " where site_id = %s and status = 'success' and id < %s",
        [site_id, run_id],
    )
    return row["id"] if row else None


async def run_change_counts(conn: AsyncConnection, run_ids: list[int]) -> dict[int, dict]:
    rows = await _all(
        conn,
        "select run_id, change, count(*) as n from recommendations"
        " where run_id = any(%s) group by 1, 2",
        [run_ids],
    )
    out: dict[int, dict] = {i: {"new": 0, "open": 0, "gone": 0, "total": 0} for i in run_ids}
    for r in rows:
        out[r["run_id"]]["total"] += r["n"]
        if r["change"] in ("new", "open", "gone"):
            out[r["run_id"]][r["change"]] += r["n"]
    return out


async def list_recommendation_runs(
    conn: AsyncConnection, site_id: str, limit: int, offset: int
) -> tuple[list[dict], int]:
    rows = await _all(
        conn,
        "select * from recommendation_runs where site_id = %s order by id desc limit %s offset %s",
        [site_id, limit, offset],
    )
    total = await _one(
        conn, "select count(*) as n from recommendation_runs where site_id = %s", [site_id]
    )
    return rows, total["n"]


async def list_recommendations(
    conn: AsyncConnection,
    run_id: int,
    pattern: str | None = None,
    confidence: str | None = None,
    change: str | None = None,
) -> list[dict]:
    conds, params = ["r.run_id = %s"], [run_id]
    for col, value in (("pattern", pattern), ("confidence", confidence), ("change", change)):
        if value:
            conds.append(f"r.{col} = %s")
            params.append(value)
    return await _all(
        conn,
        f"select r.* from recommendations r where {' and '.join(conds)}"
        " order by r.rank nulls last, r.score desc, r.id",
        params,
    )


async def get_recommendation(conn: AsyncConnection, site_id: str, rec_id: int) -> dict | None:
    rec = await _one(
        conn, "select * from recommendations where site_id = %s and id = %s", [site_id, rec_id]
    )
    if rec is None:
        return None
    rec["history"] = await _all(
        conn,
        "select run_id, id, rank, score, change from recommendations"
        " where site_id = %s and stable_id = %s order by run_id",
        [site_id, rec["stable_id"]],
    )
    rec["related"] = (
        await _all(
            conn,
            "select id, pattern, target, score, rank from recommendations"
            " where run_id = %s and journey_id = %s and id <> %s order by rank nulls last, id",
            [rec["run_id"], rec["journey_id"], rec_id],
        )
        if rec["journey_id"]
        else []
    )
    return rec


# ---------------------------------------------------------------- pipeline runs


async def list_pipeline_runs(
    conn: AsyncConnection,
    site_id: str,
    lane: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    conds, params = ["site_id = %s"], [site_id]
    for col, value in (("lane", lane), ("status", status)):
        if value:
            conds.append(f"{col} = %s")
            params.append(value)
    where = " and ".join(conds)
    rows = await _all(
        conn,
        f"""
        select id::text as id, site_id, lane, status, started_at, finished_at, failed_step,
               error, counts from pipeline_runs where {where}
        order by started_at desc, id limit %s offset %s
        """,
        [*params, limit, offset],
    )
    total = await _one(conn, f"select count(*) as n from pipeline_runs where {where}", params)
    return rows, total["n"]


async def get_pipeline_run(conn: AsyncConnection, site_id: str, run_id: str) -> dict | None:
    return await _one(
        conn,
        """
        select id::text as id, site_id, lane, status, started_at, finished_at, failed_step,
               error, counts from pipeline_runs where site_id = %s and id = %s::uuid
        """,
        [site_id, run_id],
    )


def previous_window(f: Filters) -> Filters:
    span: timedelta = f.end - f.start
    return replace(f, start=f.start - span, end=f.start)
