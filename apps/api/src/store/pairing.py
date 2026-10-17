from datetime import datetime

from psycopg import AsyncConnection

# One round: every CDN row picks its nearest origin row and every origin row its nearest CDN
# row; only mutual picks pair. Ties break on id. Rows left over compete again in the next round,
# so the result is one-to-one and nearest-first. The caller repeats until a round pairs nothing.
PAIR_ROUND = """
with cand as (
    select c.id as c_id, c.ts as c_ts, o.id as o_id, o.ts as o_ts,
           abs(extract(epoch from (c.ts - o.ts))) as diff
    from events c
    join events o
      on o.site_id = c.site_id
     and o.edge_request_id = c.edge_request_id
     and o.method is not distinct from c.method
     and o.path = c.path
     and o.ts between c.ts - make_interval(secs => %(window)s)
                  and c.ts + make_interval(secs => %(window)s)
    where c.site_id = %(site)s and c.source = 'cdn' and c.pair_state = 'pending'
      and o.source = 'origin' and o.pair_state = 'pending'
      and c.edge_request_id is not null
),
ranked as (
    select *,
           row_number() over (partition by c_id order by diff, o_id) as rn_c,
           row_number() over (partition by o_id order by diff, c_id) as rn_o
    from cand
),
chosen as (
    select c_id, c_ts, o_id, o_ts from ranked where rn_c = 1 and rn_o = 1
),
upd as (
    update events c set
        source = 'paired',
        pair_state = 'paired',
        origin_status = coalesce(o.origin_status, o.status),
        status = coalesce(c.edge_status, c.status, o.origin_status, o.status),
        request_id = coalesce(o.request_id, c.request_id),
        response_time_ms = coalesce(o.response_time_ms, c.response_time_ms),
        bytes_sent = coalesce(c.bytes_sent, o.bytes_sent),
        host = coalesce(c.host, o.host),
        referrer = coalesce(c.referrer, o.referrer),
        origin_line_key = o.line_key,
        origin_file_id = o.file_id
    from chosen ch
    join events o on o.site_id = %(site)s and o.ts = ch.o_ts and o.id = ch.o_id
    where c.site_id = %(site)s and c.ts = ch.c_ts and c.id = ch.c_id
    returning c.id
),
del as (
    delete from events o using chosen ch
    where o.site_id = %(site)s and o.ts = ch.o_ts and o.id = ch.o_id
    returning o.id
)
select (select count(*) from upd) as paired, (select count(*) from del) as deleted
"""

EXPIRE = """
with expired as (
    update events set
        pair_state = 'single',
        cdn_bypass = (source = 'origin')
    where site_id = %(site)s and pair_state = 'pending' and imported_at < %(cutoff)s
      and (
          imported_at < %(hard_cutoff)s
          or not exists (
              select 1 from import_files f
              where f.site_id = %(site)s and f.status in ('new', 'importing')
                and f.source <> events.source
          )
      )
    returning source
)
select count(*) as single, count(*) filter (where source = 'origin') as bypass from expired
"""


async def pair_pending(conn: AsyncConnection, site_id: str, window_seconds: int) -> int:
    total = 0
    params = {"site": site_id, "window": window_seconds}
    while True:
        cur = await conn.execute(PAIR_ROUND, params)
        paired = (await cur.fetchone())[0]
        if paired == 0:
            return total
        total += paired


async def expire_pending(
    conn: AsyncConnection, site_id: str, cutoff: datetime, hard_cutoff: datetime
) -> tuple[int, int]:
    # A row older than cutoff becomes single (1b.6), unless a file of the other source is still
    # queued or importing: its lines may pair with this row, and a large backfill reaches them
    # only after many ticks. Rows older than hard_cutoff expire in any case.
    cur = await conn.execute(
        EXPIRE, {"site": site_id, "cutoff": cutoff, "hard_cutoff": hard_cutoff}
    )
    single, bypass = await cur.fetchone()
    return single, bypass
