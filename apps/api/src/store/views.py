from datetime import datetime

from psycopg import AsyncConnection

# Incremental design (decision 4.1):
# - "New work" = events with in_views = false that are ready (pair_state <> 'pending', verdict set
#   and classified, client_key set). The partial index events_not_in_views holds only these rows,
#   so the cost follows the number of new events, not the size of the history. The flag is set in
#   the same transaction that builds the sessions. A late event (backfill, late CDN file, a verdict
#   that came later) has in_views = false, so it shows up by itself.
# - Events with client_key NULL (NOT GROUPED) have no verdict and no session. They count in the
#   hourly views as class 6 (UNKNOWN), agent 'unknown:ungrouped', and are flagged when done.
# - Only clients with new events are rebuilt, from the start of the first session that the
#   new events can touch (an earlier session whose last_seen is within the gap) to the end.
#   Sessions of that client from that point on are deleted and inserted again in the same
#   transaction. Normal case = the one open session. Late case (4.6) = closed sessions too.
# - Idle open sessions (no new event) move to `sessions` by a time rule only.
# - A session never lasts longer than MAX_SESSION_HOURS: the first event after that span starts
#   a new session (even without a gap). One endless client (monitor, crawler) so costs a bounded
#   rebuild.
# - Hourly rows: delete + insert from the events of the hours that hold new events, plus the
#   hours of every event whose session-derived values changed (session id, retry flag, loop
#   flag) compared with the stored rows. Never incremented, so they are idempotent.

MAX_SESSION_HOURS = 24

HOUR = "date_trunc('hour', {ts} at time zone 'UTC') at time zone 'UTC'"

# Window flags for a relation with (session_id, seq, ts, path, status).
FLAGGED = """
select b.*,
    b.seq = min(b.seq) over pp as first_of_path,
    coalesce(
        lag(b.status) over pp >= 400
        and b.ts - lag(b.ts) over pp <= %(retry)s * interval '1 second', false
    ) as is_retry,
    (
        count(*) over (partition by b.session_id, b.path) >= %(loop)s
        or (
            coalesce(lag(b.status) over ps between 300 and 399, false)
            and min(b.seq) over pp <= b.seq - 2
        )
    ) as is_loop
from {base} b
window pp as (partition by b.session_id, b.path order by b.seq),
       ps as (partition by b.session_id order by b.seq)
"""

STEPS = (
    "unnest(%(jid)s::text[], %(jno)s::int[], %(jpath)s::text[]) "
    "as t(journey_id, step_no, step_path)"
)


async def _temp(conn: AsyncConnection, name: str, select: str, params: dict) -> int:
    await conn.execute(f"drop table if exists {name}")
    cur = await conn.execute(f"create temp table {name} on commit drop as {select}", params)
    return cur.rowcount


async def stage_new_events(
    conn: AsyncConnection, site_id: str, now: datetime, gap_max_minutes: int
) -> dict:
    p = {"s": site_id, "now": now, "gapmax": gap_max_minutes}
    await _temp(
        conn,
        "_new",
        """
        select e.client_key, e.ts, e.id
        from events e join verdicts v on v.id = e.verdict_id
        where e.site_id = %(s)s and not e.in_views and e.pair_state <> 'pending'
          and v.traffic_class is not null and e.client_key is not null
        """,
        p,
    )
    clients = await _temp(
        conn,
        "_dirty",
        """
        select n.client_key, n.min_ts,
            least(n.min_ts, coalesce((
                select min(x.started) from (
                    select started, last_seen from sessions
                    where site_id = %(s)s and client_key = n.client_key
                    union all
                    select started, last_seen from open_sessions
                    where site_id = %(s)s and client_key = n.client_key
                ) x
                where x.last_seen >= n.min_ts - %(gapmax)s * interval '1 minute'
            ), n.min_ts)) as rs
        from (select client_key, min(ts) as min_ts from _new group by client_key) n
        """,
        p,
    )
    await _temp(
        conn,
        "_ungrouped",
        """
        select e.ts, e.id from events e
        where e.site_id = %(s)s and not e.in_views and e.pair_state <> 'pending'
          and e.client_key is null
        """,
        p,
    )
    await _temp(
        conn,
        "_hours",
        f"""
        select distinct {HOUR.format(ts="ts")} as hour from _new
        union
        select distinct {HOUR.format(ts="ts")} from _ungrouped
        """,
        p,
    )
    return {"clients": clients}


async def stage_sessions(conn: AsyncConnection, site_id: str, p: dict) -> int:
    p = p | {"s": site_id, "cap": MAX_SESSION_HOURS}
    # pass 1: events of dirty clients from their range start, with verdict; break flag per gap
    await _temp(
        conn,
        "_ev0",
        """
        select e.id, e.ts, e.client_key, e.path, e.status, e.source, e.cdn_bypass, e.verdict_id,
            e.edge_signal, e.user_agent, e.client_ip,
            v.traffic_class, v.claimed_agent, v.registry_category, v.verdict,
            case when (last_value(v.registry_category) over c) = 'agent_client'
                 then %(agent_gap)s else %(gap)s end as gap_min
        from events e
        join _dirty d on d.client_key = e.client_key
        join verdicts v on v.id = e.verdict_id
        where e.site_id = %(s)s and e.ts >= d.rs and e.pair_state <> 'pending'
          and v.traffic_class is not null
        window c as (
            partition by e.client_key order by e.ts, e.id
            rows between unbounded preceding and unbounded following
        )
        """,
        p,
    )
    await _temp(
        conn,
        "_ev0r",
        """
        select a.*, row_number() over w as rn,
            (lag(a.ts) over w is null
                or a.ts - lag(a.ts) over w > a.gap_min * interval '1 minute') as brk
        from _ev0 a
        window w as (partition by a.client_key order by a.ts, a.id)
        """,
        p,
    )
    await conn.execute("create index on _ev0r (client_key, rn)")
    # Session starts: the first event, then the first event after it that follows a gap or lies
    # more than MAX_SESSION_HOURS after the session start. Starts come from a real start, so a
    # rebuild from the start of a stored session gives the same cuts.
    await _temp(
        conn,
        "_starts",
        """
        with recursive st(client_key, rn, ts) as (
            select client_key, rn, ts from _ev0r where rn = 1
            union all
            select n.client_key, n.rn, n.ts from st s
            cross join lateral (
                select e.client_key, e.rn, e.ts from _ev0r e
                where e.client_key = s.client_key and e.rn > s.rn
                  and (e.brk or e.ts > s.ts + %(cap)s * interval '1 hour')
                order by e.rn limit 1
            ) n
        )
        select client_key, rn from st
        """,
        p,
    )
    await _temp(
        conn,
        "_ev1",
        """
        select x.*,
            's' || left(md5(%(s)s || '|' || x.client_key || '|' ||
                to_char(x.started at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '|' ||
                x.first_id::text), 20) as session_id,
            row_number() over (partition by x.client_key, x.session_no order by x.ts, x.id) as seq,
            row_number() over (
                partition by x.client_key, x.session_no order by x.ts desc, x.id desc
            ) = 1 as is_last
        from (
            select y.*, min(y.ts) over (partition by y.client_key, y.session_no) as started,
                first_value(y.id) over (
                    partition by y.client_key, y.session_no order by y.ts, y.id) as first_id
            from (
                select a.*, sum((st.rn is not null)::int) over (
                    partition by a.client_key order by a.ts, a.id) as session_no
                from _ev0r a
                left join _starts st on st.client_key = a.client_key and st.rn = a.rn
            ) y
        ) x
        """,
        p,
    )
    await _temp(conn, "_ev", FLAGGED.format(base="_ev1"), p)
    await _temp(
        conn,
        "_sess",
        f"""
        select s.session_id, s.client_key,
            min(s.ts) as started, max(s.ts) as last_seen, count(*)::int as requests,
            (count(*) filter (where s.first_of_path))::int as distinct_pages,
            coalesce(array_agg(s.path order by s.seq) filter (where s.first_of_path), '{{}}')
                as pages_in_order,
            (count(*) filter (where s.first_of_path and (
                s.path = any(%(key)s::text[]) or split_part(s.path, '?', 1) = any(%(key)s::text[])
            )))::int as key_pages_visited,
            coalesce(bool_or(s.status < 400 and (
                s.path = any(%(conv)s::text[]) or split_part(s.path, '?', 1) = any(%(conv)s::text[])
            )), false) as reached_conversion,
            (count(*) filter (where s.is_retry))::int as retries,
            coalesce(bool_or(s.is_loop), false) as has_loop,
            array(select distinct u from unnest(
                coalesce(array_agg(s.path) filter (where s.is_retry or s.is_loop), '{{}}')
                || coalesce(
                    array_agg(split_part(s.path, '?', 1)) filter (where s.is_retry or s.is_loop),
                    '{{}}')
            ) u) as retry_paths,
            max(s.gap_min) as gap_min,
            (array_agg(s.verdict_id order by s.seq desc))[1] as verdict_id,
            (array_agg(s.claimed_agent order by s.seq desc))[1] as claimed_agent,
            (array_agg(s.registry_category order by s.seq desc))[1] as registry_category,
            (array_agg(s.verdict order by s.seq desc))[1] as verdict,
            (array_agg(s.user_agent order by s.seq desc))[1] as user_agent,
            (array_agg(s.client_ip order by s.seq desc))[1] as client_ip,
            (array_agg(s.edge_signal order by s.seq desc))[1] as edge_signal,
            (array_agg(s.traffic_class order by s.seq desc))[1] as traffic_class,
            coalesce((
                select jsonb_object_agg(c.status::text, c.n) from (
                    select status, count(*) as n from _ev
                    where session_id = s.session_id and status is not null group by status
                ) c
            ), '{{}}'::jsonb) as status_counts,
            coalesce((
                select jsonb_object_agg(j.journey_id, j.hi) from (
                    select t.journey_id, max(t.step_no) as hi
                    from _ev e2 join {STEPS}
                      on t.step_path in (e2.path, split_part(e2.path, '?', 1))
                    where e2.session_id = s.session_id group by t.journey_id
                ) j
            ), '{{}}'::jsonb) as journeys_reached,
            false as shared_ip,
            null::text as confidence,
            '{{}}'::text[] as gaps
        from _ev s
        group by s.session_id, s.client_key
        """,
        p,
    )
    cur = await conn.execute("select count(*) from _sess")
    return (await cur.fetchone())[0]


async def session_ips(conn: AsyncConnection) -> list[str]:
    cur = await conn.execute(
        "select distinct host(client_ip) from _sess where client_ip is not null"
    )
    return [r[0] for r in await cur.fetchall()]


async def finish_sessions(
    conn: AsyncConnection, site_id: str, p: dict, shared_ips: list[str], base_gaps: list[str]
) -> dict:
    p = p | {"s": site_id, "shared": shared_ips, "base_gaps": base_gaps}
    await conn.execute(
        "update _sess set shared_ip = true where host(client_ip) = any(%(shared)s::text[])", p
    )
    await conn.execute(
        """
        update _sess set
            confidence = case
                when shared_ip or registry_category = 'agent_client' or traffic_class = 6
                    then 'low'
                when verdict = 'VERIFIED' then 'high'
                when verdict = 'CLAIMED' or traffic_class in (4, 5) then 'medium'
                else 'low' end,
            gaps = %(base_gaps)s::text[]
                || case when shared_ip then array['shared IP: may contain more than one agent']
                        else '{}'::text[] end
        """,
        p,
    )
    await _temp(
        conn,
        "_old",
        """
        select session_id, version, client_key, started, last_seen, true as closed
        from sessions s
        where site_id = %(s)s and exists (
            select 1 from _dirty d where d.client_key = s.client_key and s.started >= d.rs)
        union all
        select session_id, version, client_key, started, last_seen, false
        from open_sessions s
        where site_id = %(s)s and exists (
            select 1 from _dirty d where d.client_key = s.client_key and s.started >= d.rs)
        """,
        p,
    )
    # Stable ids: a rebuilt session keeps the id of the oldest stored session it overlaps. A late
    # earlier event moves `started` but not the id, so links and recommendation evidence stay
    # valid. When sessions merge, the merged one keeps the earliest id. Each old id goes to one
    # rebuilt session at most (one-to-one). Any other rebuilt session gets its own hash id, and
    # that id is changed until it differs from every id that is in use: the ids of the other
    # rebuilt sessions, every id that was stored in the range, and every stored id outside it.
    await _temp(
        conn,
        "_idmap",
        """
        select distinct on (x.new_id) x.new_id, x.old_id from (
            select distinct on (o.session_id)
                n.session_id as new_id, o.session_id as old_id, o.started as old_started
            from _sess n join _old o
              on o.client_key = n.client_key and o.started <= n.last_seen
             and o.last_seen >= n.started
            order by o.session_id, n.started
        ) x
        order by x.new_id, x.old_started
        """,
        p,
    )
    await _temp(
        conn,
        "_final",
        """
        select n.session_id as new_id, coalesce(m.old_id, n.session_id) as final_id,
            m.old_id is not null as mapped
        from _sess n left join _idmap m on m.new_id = n.session_id
        """,
        p,
    )
    await conn.execute("create index on _final (final_id)")
    for _ in range(20):
        cur = await conn.execute(
            """
            update _final f set final_id = 's' || left(md5(f.final_id || '|rehash'), 20)
            where not f.mapped and (
                exists (select 1 from _final g where g.final_id = f.final_id
                        and g.new_id <> f.new_id and (g.mapped or g.new_id < f.new_id))
                or exists (select 1 from _old o where o.session_id = f.final_id)
                or exists (select 1 from sessions x
                           where x.site_id = %(s)s and x.session_id = f.final_id)
                or exists (select 1 from open_sessions x
                           where x.site_id = %(s)s and x.session_id = f.final_id)
            )
            """,
            p,
        )
        if not cur.rowcount:
            break
    else:
        raise RuntimeError("could not find free session ids")
    for table in ("_sess", "_ev"):
        await conn.execute(
            f"update {table} t set session_id = m.final_id from _final m "
            "where t.session_id = m.new_id"
        )
    # Stored state of the events in the range, before the old rows are deleted.
    await _temp(
        conn,
        "_oldev",
        "select f.session_id, f.ts, f.id, f.is_retry, f.is_loop from ("
        + FLAGGED.format(
            base="""(
                select se.session_id, se.seq, se.event_ts as ts, se.event_id as id, e.path,
                    e.status
                from session_events se
                join events e on e.site_id = se.site_id and e.ts = se.event_ts
                    and e.id = se.event_id
                where se.site_id = %(s)s and se.session_id in (select session_id from _old)
            )"""
        )
        + ") f",
        p,
    )
    # Hours that change: hours of events that are new in a session, or whose stored session id,
    # retry flag or loop flag differs from the rebuilt value (growth, merge, split, late event).
    # Hours of the new events are already in _hours. Unchanged events cost nothing, so the work
    # does not follow the length of a session.
    await conn.execute(
        f"""
        insert into _hours
        select distinct {HOUR.format(ts="c.ts")} from (
            select coalesce(n.ts, o.ts) as ts
            from _ev n full join _oldev o on o.id = n.id and o.ts = n.ts
            where n.id is null or o.id is null
               or n.session_id is distinct from o.session_id
               or n.is_retry is distinct from o.is_retry
               or n.is_loop is distinct from o.is_loop
        ) c
        except select hour from _hours
        """
    )
    cur = await conn.execute("select count(*) from _old where closed")
    recomputed_closed = (await cur.fetchone())[0]
    await conn.execute(
        "delete from session_events where site_id = %(s)s "
        "and session_id in (select session_id from _old)",
        p,
    )
    for table in ("sessions", "open_sessions"):
        await conn.execute(
            f"""
            delete from {table} s where site_id = %(s)s and exists (
                select 1 from _dirty d where d.client_key = s.client_key and s.started >= d.rs)
            """,
            p,
        )
    columns = """
        site_id, session_id, version, client_key, verdict_id, claimed_agent, user_agent,
        client_ip, edge_signal, traffic_class, confidence, started, last_seen, requests,
        distinct_pages, pages_in_order, key_pages_visited, reached_conversion, has_retry,
        has_loop, retries, shared_ip, gaps, status_counts, journeys_reached, retry_paths
    """
    select = """
        select %(s)s, n.session_id, coalesce(o.version, 0) + 1, n.client_key, n.verdict_id,
            n.claimed_agent, n.user_agent, n.client_ip, n.edge_signal, n.traffic_class,
            n.confidence, n.started, n.last_seen, n.requests, n.distinct_pages,
            n.pages_in_order, n.key_pages_visited, n.reached_conversion, n.retries > 0,
            n.has_loop, n.retries, n.shared_ip, n.gaps, n.status_counts, n.journeys_reached,
            n.retry_paths
        from _sess n left join (
            select session_id, max(version) as version from _old group by session_id
        ) o using (session_id)
        where {cond}
    """
    cond_open = "n.last_seen + (n.gap_min + %(margin)s) * interval '1 minute' > %(now)s"
    cur = await conn.execute(
        f"insert into open_sessions ({columns}) " + select.format(cond=cond_open), p
    )
    opened = cur.rowcount
    cur = await conn.execute(
        f"insert into sessions ({columns}) " + select.format(cond=f"not ({cond_open})"), p
    )
    closed = cur.rowcount
    await conn.execute(
        """
        insert into session_events (site_id, session_id, event_id, event_ts, seq)
        select %(s)s, session_id, id, ts, seq from _ev
        """,
        p,
    )
    return {"open": opened, "closed": closed, "recomputed_closed": recomputed_closed}


async def close_idle_sessions(
    conn: AsyncConnection,
    site_id: str,
    now: datetime,
    gap: int,
    agent_gap: int,
    margin: int,
) -> int:
    cur = await conn.execute(
        """
        with moved as (
            delete from open_sessions o
            where o.site_id = %(s)s
              and o.last_seen + (
                    case when (select v.registry_category from verdicts v where v.id = o.verdict_id)
                              = 'agent_client' then %(agent_gap)s else %(gap)s end
                    + %(margin)s) * interval '1 minute' <= %(now)s
            returning o.*
        )
        insert into sessions select * from moved
        on conflict (site_id, session_id) do nothing
        """,
        {"s": site_id, "now": now, "gap": gap, "agent_gap": agent_gap, "margin": margin},
    )
    return cur.rowcount


async def refresh_hours(conn: AsyncConnection, site_id: str, p: dict) -> int:
    p = p | {"s": site_id}
    cur = await conn.execute("select count(*) from _hours")
    hours = (await cur.fetchone())[0]
    if not hours:
        return 0
    await _temp(
        conn,
        "_he",
        """
        select e.id, e.ts, h.hour, e.client_key, e.path, e.status, e.bytes_sent,
            coalesce(v.traffic_class, 6) as traffic_class,
            coalesce(v.verdict, 'UNKNOWN') as verdict,
            v.confidence, se.session_id, se.seq,
            case when e.client_key is null then 'unknown:ungrouped'
                 else coalesce(v.claimed_agent,
                     'unknown:' || coalesce(v.ua_type, 'class' || v.traffic_class)) end as agent
        from events e
        left join verdicts v on v.id = e.verdict_id
        join _hours h on e.ts >= h.hour and e.ts < h.hour + interval '1 hour'
        left join session_events se
            on se.site_id = e.site_id and se.event_id = e.id and se.event_ts = e.ts
        where e.site_id = %(s)s and e.pair_state <> 'pending'
          and (v.traffic_class is not null or e.client_key is null)
        """,
        p,
    )
    await _temp(
        conn,
        "_hflags",
        "select f.session_id, f.seq, f.is_retry, f.is_loop from ("
        + FLAGGED.format(
            base="""(
                select se.session_id, se.seq, e.ts, e.path, e.status
                from session_events se
                join events e on e.site_id = se.site_id and e.ts = se.event_ts
                    and e.id = se.event_id
                where se.site_id = %(s)s
                  and se.session_id in (select session_id from _he where session_id is not null)
            )"""
        )
        + ") f",
        p,
    )
    await conn.execute(
        "create index on _hflags (session_id, seq)",
    )
    await _temp(
        conn,
        "_hx",
        """
        select h.*, coalesce(f.is_retry, false) as is_retry, coalesce(f.is_loop, false) as is_loop
        from _he h left join _hflags f on f.session_id = h.session_id and f.seq = h.seq
        """,
        p,
    )
    for table in ("page_stats", "agents", "journey_steps"):
        await conn.execute(
            f"delete from {table} where site_id = %(s)s and hour in (select hour from _hours)", p
        )
    # n_4xx counts every 4xx (403 and 429 included); error rate = (n_4xx + n_5xx) / requests
    await conn.execute(
        """
        insert into page_stats (site_id, hour, path, traffic_class, tags, requests, sessions,
            clients, median_bytes, n_2xx, n_3xx, n_403, n_429, n_4xx, n_5xx, retries)
        select %(s)s, hour, path, traffic_class,
            array_remove(array[
                case when path = any(%(key)s::text[])
                          or split_part(path, '?', 1) = any(%(key)s::text[]) then 'key' end,
                case when path = any(%(conv)s::text[])
                          or split_part(path, '?', 1) = any(%(conv)s::text[]) then 'conversion' end
            ], null),
            count(*), count(distinct session_id), count(distinct client_key),
            (percentile_cont(0.5) within group (order by bytes_sent))::bigint,
            count(*) filter (where status between 200 and 299),
            count(*) filter (where status between 300 and 399),
            count(*) filter (where status = 403),
            count(*) filter (where status = 429),
            count(*) filter (where status between 400 and 499),
            count(*) filter (where status between 500 and 599),
            count(*) filter (where is_retry)
        from _hx group by hour, path, traffic_class
        """,
        p,
    )
    await conn.execute(
        """
        insert into agents (site_id, hour, claimed_agent, traffic_class, verification, confidence,
            first_seen, last_seen, requests, sessions, distinct_pages, top_paths)
        select %(s)s, x.hour, x.agent, x.traffic_class,
            (array_agg(x.verdict order by x.ts desc, x.id desc))[1],
            (array_agg(x.confidence order by x.ts desc, x.id desc))[1],
            min(x.ts), max(x.ts), count(*), count(distinct x.session_id),
            count(distinct x.path),
            (select array_agg(t.path order by t.n desc, t.path) from (
                select path, count(*) as n from _hx y
                where y.hour = x.hour and y.agent = x.agent and y.traffic_class = x.traffic_class
                group by path order by n desc, path limit 5) t)
        from _hx x group by x.hour, x.agent, x.traffic_class
        """,
        p,
    )
    await conn.execute(
        f"""
        with steps as (select * from {STEPS}),
        hit as (
            select h.hour, h.session_id, h.traffic_class, s.journey_id, s.step_no,
                (h.is_retry or h.is_loop) as rl
            from _hx h join steps s on s.step_path in (h.path, split_part(h.path, '?', 1))
            where h.session_id is not null
        ),
        hi as (
            select hour, session_id, traffic_class, journey_id, max(step_no) as hi
            from hit group by 1, 2, 3, 4
        ),
        rl as (
            select distinct hour, session_id, traffic_class, journey_id, step_no
            from hit where rl
        )
        insert into journey_steps (site_id, hour, journey_id, traffic_class, step_no, step_path,
            sessions_reached, sessions_retry_or_loop)
        select %(s)s, hi.hour, st.journey_id, hi.traffic_class, st.step_no, st.step_path,
            count(*),
            count(*) filter (where exists (
                select 1 from rl where rl.hour = hi.hour and rl.session_id = hi.session_id
                  and rl.traffic_class = hi.traffic_class and rl.journey_id = st.journey_id
                  and rl.step_no = st.step_no))
        from hi join steps st on st.journey_id = hi.journey_id and st.step_no <= hi.hi
        group by hi.hour, st.journey_id, hi.traffic_class, st.step_no, st.step_path
        """,
        p,
    )
    return hours


async def reset_site(conn: AsyncConnection, site_id: str) -> int:
    # Full rebuild after events were removed (an import file was deleted). The incremental path
    # only adds: it cannot see that rows are gone. All views of the site are deleted and every
    # event is new work again, so the next views step builds them from the events that remain.
    for table in ("session_events", "sessions", "open_sessions", "page_stats", "journey_steps",
                  "agents"):  # fmt: skip
        await conn.execute(f"delete from {table} where site_id = %s", [site_id])
    cur = await conn.execute(
        "update events set in_views = false where site_id = %s and in_views", [site_id]
    )
    return cur.rowcount


async def mark_in_views(conn: AsyncConnection, site_id: str) -> int:
    # Flag the staged events as done. Same transaction as the session rows.
    cur = await conn.execute(
        """
        update events e set in_views = true
        from (select ts, id from _new union all select ts, id from _ungrouped) n
        where e.site_id = %s and e.ts = n.ts and e.id = n.id
        """,
        [site_id],
    )
    return cur.rowcount
