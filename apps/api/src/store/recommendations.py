from datetime import UTC, datetime

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ID_CAP = 5000  # Session IDs kept for each candidate. The count is always exact.

# Sessions in the window: closed + still open. MATERIALIZED: the window set is read once (index
# on (site_id, last_seen)) and every candidate works on that set, never on the full history.
_SESS = """
sess as materialized (
    select * from sessions where site_id = %(site)s and last_seen >= %(start)s
    union all
    select * from open_sessions where site_id = %(site)s and last_seen >= %(start)s
)
"""

# Aggregate over the matching sessions (used inside a lateral join).
_AGG = """
count(*) as sessions_count,
coalesce((array_agg(s.session_id order by s.last_seen desc))[1:%(cap)s], '{}') as session_ids,
count(*) filter (where s.confidence = 'high') as n_high,
count(*) filter (where s.confidence = 'medium') as n_medium,
count(*) filter (where s.confidence not in ('high', 'medium') or s.confidence is null) as n_low
"""


async def _rows(conn: AsyncConnection, query: str, params: dict) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, params)
        return await cur.fetchall()


def _params(site_id: str, start: datetime, **extra) -> dict:
    # Hours are UTC hours (page_stats.hour is written in UTC), whatever the zone of `start`.
    start = start.astimezone(UTC)
    hour_start = start.replace(minute=0, second=0, microsecond=0)
    return {"site": site_id, "start": start, "hour_start": hour_start, "cap": ID_CAP} | extra


async def p1_product_discovery(
    conn: AsyncConnection, site_id: str, start: datetime, min_key_pages: int
) -> dict | None:
    query = f"""
    with {_SESS}
    select {_AGG} from sess s
    where s.traffic_class in (2, 4) and s.key_pages_visited >= %(min_pages)s
      and not s.reached_conversion
    having count(*) > 0
    """
    rows = await _rows(conn, query, _params(site_id, start, min_pages=min_key_pages))
    return rows[0] if rows else None


async def p2_blocked_access(
    conn: AsyncConnection, site_id: str, start: datetime, pages: list[str], min_blocks: int
) -> list[dict]:
    query = f"""
    with {_SESS},
    blocked as (
        select path, sum(n_403 + n_429)::int as blocks, sum(n_403)::int as n_403,
               sum(n_429)::int as n_429, sum(requests)::int as requests
        from page_stats
        where site_id = %(site)s and hour >= %(hour_start)s and traffic_class in (1, 2)
          and path = any(%(pages)s)
        group by path
        having sum(n_403 + n_429) >= %(min_blocks)s
    )
    select b.*, a.* from blocked b
    left join lateral (
        select {_AGG} from sess s
        where s.traffic_class in (1, 2)
          and s.pages_in_order @> array[b.path]::text[]
          and jsonb_exists_any(s.status_counts, array['403', '429'])
    ) a on true
    order by b.blocks desc, b.path
    """
    return await _rows(conn, query, _params(site_id, start, pages=pages, min_blocks=min_blocks))


async def p3_broken_navigation(
    conn: AsyncConnection, site_id: str, start: datetime, min_sessions: int
) -> list[dict]:
    # Distinct sessions: hourly rows list the steps only. A session counts once, at a
    # step where it had a retry or a loop (retry_paths), however many hours it spans.
    query = f"""
    with {_SESS},
    steps as (
        select distinct journey_id, step_no, step_path
        from journey_steps
        where site_id = %(site)s and hour >= %(hour_start)s and traffic_class in (2, 4)
    )
    select st.*, a.*, a.sessions_count as affected from steps st
    cross join lateral (
        select {_AGG} from sess s
        where s.traffic_class in (2, 4) and s.retry_paths @> array[st.step_path]::text[]
          and jsonb_exists(s.journeys_reached, st.journey_id)
    ) a
    where a.sessions_count >= %(min_sessions)s
    order by a.sessions_count desc, st.journey_id, st.step_no
    """
    return await _rows(conn, query, _params(site_id, start, min_sessions=min_sessions))


async def p4_content_discovery(
    conn: AsyncConnection, site_id: str, start: datetime, pages: list[str], bytes_ratio: float
) -> list[dict]:
    query = f"""
    with {_SESS},
    stats as (
        select path, traffic_class, sum(requests)::int as requests, sum(n_2xx)::int as n_2xx,
               sum(n_3xx)::int as n_3xx, sum(n_403)::int as n_403,
               percentile_disc(0.5) within group (order by median_bytes) as median_bytes
        from page_stats
        where site_id = %(site)s and hour >= %(hour_start)s and traffic_class in (2, 5)
          and path = any(%(pages)s)
        group by path, traffic_class
    ),
    pages as (
        select p.path,
               coalesce(a.requests, 0) as requests, coalesce(a.n_2xx, 0) as n_2xx,
               coalesce(a.n_3xx, 0) as n_3xx, coalesce(a.n_403, 0) as n_403,
               a.median_bytes as ai_median_bytes, b.median_bytes as browser_median_bytes
        from unnest(%(pages)s::text[]) as p(path)
        left join stats a on a.path = p.path and a.traffic_class = 2
        left join stats b on b.path = p.path and b.traffic_class = 5
    ),
    found as (
        select *, case
            when requests = 0 then 'never_fetched'
            when n_2xx = 0 and n_403 + n_3xx > 0 then 'blocked_or_redirected'
            when n_2xx > 0 and browser_median_bytes > 0
                 and ai_median_bytes < %(ratio)s * browser_median_bytes then 'small_response'
        end as kind
        from pages
    )
    select f.*, a.* from found f
    left join lateral (
        select {_AGG} from sess s
        where s.traffic_class = 2 and s.pages_in_order @> array[f.path]::text[]
    ) a on true
    where f.kind is not null
      and exists (
        select 1 from page_stats
        where site_id = %(site)s and hour >= %(hour_start)s and traffic_class = 2
          and requests > 0
      )
    order by f.path
    """
    return await _rows(conn, query, _params(site_id, start, pages=pages, ratio=bytes_ratio))


async def p5_full_journey(
    conn: AsyncConnection, site_id: str, start: datetime, journeys: list[dict]
) -> list[dict]:
    # journeys: [{"id", "first_path", "final_no", "final_path"}] (critical journeys).
    if not journeys:
        return []
    query = f"""
    with {_SESS},
    j as (
        select * from unnest(
            %(ids)s::text[], %(finals)s::int[], %(firsts)s::text[], %(final_paths)s::text[]
        ) as t(journey_id, final_no, first_path, final_path)
    ),
    reach as (
        select j.*,
            (select count(*) from sess s where s.traffic_class in (2, 4)
                and coalesce((s.journeys_reached ->> j.journey_id)::int, 0) >= 1)::int
                as first_reached,
            (select count(*) from sess s where s.traffic_class in (2, 4)
                and coalesce((s.journeys_reached ->> j.journey_id)::int, 0) >= j.final_no)::int
                as final_reached
        from j
    )
    select r.*, a.* from reach r
    left join lateral (
        select {_AGG} from sess s
        where s.traffic_class in (2, 4)
          and s.pages_in_order @> array[r.first_path]::text[]
          and not s.pages_in_order @> array[r.final_path]::text[]
    ) a on true
    where r.first_reached > 0 and r.final_reached = 0
    order by r.journey_id
    """
    params = _params(
        site_id,
        start,
        ids=[j["id"] for j in journeys],
        finals=[j["final_no"] for j in journeys],
        firsts=[j["first_path"] for j in journeys],
        final_paths=[j["final_path"] for j in journeys],
    )
    return await _rows(conn, query, params)


async def class_status(
    conn: AsyncConnection, site_id: str, start: datetime, paths: list[str]
) -> list[dict]:
    query = """
    select traffic_class, sum(requests)::int as requests, sum(n_2xx)::int as n_2xx,
           sum(n_3xx)::int as n_3xx, sum(n_403)::int as n_403, sum(n_429)::int as n_429,
           sum(n_4xx)::int as n_4xx, sum(n_5xx)::int as n_5xx,
           percentile_disc(0.5) within group (order by median_bytes) as median_bytes
    from page_stats
    where site_id = %(site)s and hour >= %(hour_start)s and path = any(%(paths)s)
    group by traffic_class order by traffic_class
    """
    return await _rows(conn, query, _params(site_id, start, paths=paths))


async def agents_for_sessions(
    conn: AsyncConnection, site_id: str, start: datetime, session_ids: list[str], paths: list[str]
) -> list[dict]:
    if session_ids:
        query = f"""
        with {_SESS}
        select s.claimed_agent as agent, s.traffic_class, count(*)::int as sessions,
               (select a.verification from agents a
                where a.site_id = %(site)s and a.claimed_agent = s.claimed_agent
                  and a.traffic_class = s.traffic_class
                order by a.hour desc limit 1) as verification
        from sess s
        where s.session_id = any(%(ids)s) and s.claimed_agent is not null
        group by s.claimed_agent, s.traffic_class
        order by sessions desc, agent
        limit 10
        """
        return await _rows(conn, query, _params(site_id, start, ids=session_ids))
    query = """
    select claimed_agent as agent, traffic_class, sum(sessions)::int as sessions,
           (array_agg(verification order by hour desc))[1] as verification
    from agents
    where site_id = %(site)s and hour >= %(hour_start)s and top_paths && %(paths)s::text[]
    group by claimed_agent, traffic_class
    order by sessions desc, agent
    limit 10
    """
    return await _rows(conn, query, _params(site_id, start, paths=paths))


async def time_pattern(
    conn: AsyncConnection, site_id: str, start: datetime, session_ids: list[str], paths: list[str]
) -> dict:
    if session_ids:
        query = f"""
        with {_SESS}
        select min(started) as first_seen, max(last_seen) as last_seen,
               count(*)::int as sessions
        from sess where session_id = any(%(ids)s)
        """
        rows = await _rows(conn, query, _params(site_id, start, ids=session_ids))
        hours = await _rows(
            conn,
            f"""
            with {_SESS}
            select extract(hour from started at time zone 'UTC')::int as hour_utc,
                   count(*)::int as sessions
            from sess where session_id = any(%(ids)s)
            group by 1 order by sessions desc, 1 limit 3
            """,
            _params(site_id, start, ids=session_ids),
        )
    else:
        query = """
        select min(hour) as first_seen, max(hour) as last_seen, 0 as sessions
        from page_stats
        where site_id = %(site)s and hour >= %(hour_start)s and path = any(%(paths)s)
          and requests > 0
        """
        rows = await _rows(conn, query, _params(site_id, start, paths=paths))
        hours = []
    row = rows[0] if rows else {}
    return {
        "first_seen": row.get("first_seen"),
        "last_seen": row.get("last_seen"),
        "peak_hours_utc": [h["hour_utc"] for h in hours],
    }


async def journey_funnel(
    conn: AsyncConnection, site_id: str, start: datetime, journey_ids: list[str]
) -> list[dict]:
    # Distinct sessions from the session tables (journeys_reached, retry_paths), not hourly sums.
    query = f"""
    with {_SESS},
    steps as (
        select distinct journey_id, step_no, step_path
        from journey_steps
        where site_id = %(site)s and hour >= %(hour_start)s and journey_id = any(%(ids)s)
          and traffic_class in (2, 4)
    )
    select st.journey_id, st.step_no, st.step_path,
        (select count(*) from sess s where s.traffic_class in (2, 4)
            and coalesce((s.journeys_reached ->> st.journey_id)::int, 0) >= st.step_no)::int
            as sessions_reached,
        (select count(*) from sess s where s.traffic_class in (2, 4)
            and s.retry_paths @> array[st.step_path]::text[]
            and jsonb_exists(s.journeys_reached, st.journey_id))::int as sessions_retry_or_loop
    from steps st
    order by st.journey_id, st.step_no
    """
    return await _rows(conn, query, _params(site_id, start, ids=journey_ids))


async def count_events(conn: AsyncConnection, site_id: str, session_ids: list[str]) -> int:
    if not session_ids:
        return 0
    async with conn.cursor() as cur:
        await cur.execute(
            "select count(*) from session_events where site_id = %s and session_id = any(%s)",
            [site_id, session_ids],
        )
        return (await cur.fetchone())[0]


async def sample_events(
    conn: AsyncConnection, site_id: str, session_ids: list[str], paths: list[str], limit: int = 5
) -> list[dict]:
    if not session_ids:
        return []
    query = """
    select ev.id, ev.ts, ev.method, ev.path, ev.status
    from session_events se
    join events ev on ev.site_id = se.site_id and ev.id = se.event_id and ev.ts = se.event_ts
    where se.site_id = %s and se.session_id = any(%s)
    order by (ev.path = any(%s)) desc, (ev.status >= 400) desc, ev.ts desc, ev.id
    limit %s
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, [site_id, session_ids, paths, limit])
        return await cur.fetchall()


async def event_ids(conn: AsyncConnection, site_id: str, session_ids: list[str]) -> list[int]:
    if not session_ids:
        return []
    async with conn.cursor() as cur:
        await cur.execute(
            "select event_id from session_events where site_id = %s and session_id = any(%s)"
            " order by event_ts desc, event_id limit %s",
            [site_id, session_ids, ID_CAP],
        )
        return [r[0] for r in await cur.fetchall()]


async def create_run(
    conn: AsyncConnection,
    site_id: str,
    window: str,
    window_start: datetime,
    window_end: datetime,
    rule_version: str,
    prompt_version: str,
    model: str | None,
) -> int:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            insert into recommendation_runs
                (site_id, window_size, window_start, window_end, rule_version, prompt_version,
                 model, status, started_at)
            values (%s, %s, %s, %s, %s, %s, %s, 'running', %s)
            returning id
            """,
            [
                site_id,
                window,
                window_start,
                window_end,
                rule_version,
                prompt_version,
                model,
                window_end,
            ],
        )
        return (await cur.fetchone())[0]


async def finish_run(
    conn: AsyncConnection, run_id: int, counts: dict, finished_at: datetime
) -> None:
    await conn.execute(
        "update recommendation_runs set status = 'success', counts = %s, finished_at = %s"
        " where id = %s",
        [Jsonb(counts), finished_at, run_id],
    )


async def previous_items(conn: AsyncConnection, site_id: str, before_run_id: int) -> list[dict]:
    # Items of the latest successful run before this one. Items marked gone are not present.
    query = """
    select r.* from recommendations r
    where r.run_id = (
        select max(id) from recommendation_runs
        where site_id = %s and status = 'success' and id < %s
    ) and r.change is distinct from 'gone'
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, [site_id, before_run_id])
        return await cur.fetchall()


_COLUMNS = [
    "run_id", "site_id", "stable_id", "rank", "pattern", "target", "journey_id", "score",
    "impact", "frequency", "severity", "confidence_factor", "confidence", "factor_reasons",
    "recommended_test", "reason", "evidence", "sessions_count", "events_count",
    "potential_issue", "suggested_validation", "next_action", "text_source", "model",
    "prompt_version", "change", "bundle",
]  # fmt: skip
_JSON = {"factor_reasons", "evidence", "bundle"}


async def insert_recommendations(conn: AsyncConnection, items: list[dict]) -> None:
    if not items:
        return
    columns = ", ".join(_COLUMNS)
    marks = ", ".join(["%s"] * len(_COLUMNS))
    rows = [[Jsonb(i[c]) if c in _JSON else i.get(c) for c in _COLUMNS] for i in items]
    async with conn.cursor() as cur:
        await cur.executemany(f"insert into recommendations ({columns}) values ({marks})", rows)


async def cached_text(
    conn: AsyncConnection, site_id: str, bundle_hash: str, model: str, prompt_version: str
) -> dict | None:
    async with conn.cursor() as cur:
        await cur.execute(
            "select text from llm_text_cache where bundle_hash = %s and site_id = %s"
            " and model = %s and prompt_version = %s",
            [bundle_hash, site_id, model, prompt_version],
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def save_cached_text(
    conn: AsyncConnection,
    site_id: str,
    bundle_hash: str,
    text: dict,
    model: str,
    prompt_version: str,
) -> None:
    await conn.execute(
        """
        insert into llm_text_cache (bundle_hash, site_id, text, model, prompt_version)
        values (%s, %s, %s, %s, %s)
        on conflict (bundle_hash) do update
            set text = excluded.text, model = excluded.model,
                prompt_version = excluded.prompt_version, site_id = excluded.site_id,
                created_at = now()
        """,
        [bundle_hash, site_id, Jsonb(text), model, prompt_version],
    )
