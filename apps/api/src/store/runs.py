from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.models.domain import Lane, RunStatus


async def start_run(conn: AsyncConnection, site_id: str, lane: Lane) -> str:
    cur = await conn.execute(
        "insert into pipeline_runs (site_id, lane) values (%s, %s) returning id",
        [site_id, Lane(lane).value],
    )
    return str((await cur.fetchone())[0])


async def finish_run(
    conn: AsyncConnection,
    run_id: str,
    status: RunStatus,
    failed_step: str | None = None,
    error: str | None = None,
    counts: dict | None = None,
) -> None:
    await conn.execute(
        """
        update pipeline_runs
        set status = %s, failed_step = %s, error = %s, counts = %s, finished_at = now()
        where id = %s
        """,
        [RunStatus(status).value, failed_step, error, Jsonb(counts or {}), run_id],
    )


async def running_runs_started_before(conn: AsyncConnection, cutoff) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "select id, site_id, lane from pipeline_runs "
            "where status = 'running' and started_at < %s order by started_at",
            [cutoff],
        )
        return await cur.fetchall()


async def fail_running_run(conn: AsyncConnection, run_id: str, error: str) -> bool:
    cur = await conn.execute(
        """
        update pipeline_runs set status = 'failed', error = %s, finished_at = now()
        where id = %s and status = 'running'
        """,
        [error, str(run_id)],
    )
    return cur.rowcount > 0


async def last_success_by_lane(conn: AsyncConnection, site_ids: list[str]) -> list[dict]:
    # One index probe for each (site, lane) on pipeline_runs_site: no scan of all runs.
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select s.site_id, l.lane, (
                select r.finished_at from pipeline_runs r
                where r.site_id = s.site_id and r.lane = l.lane and r.status = 'success'
                order by r.started_at desc limit 1
            ) as last_success
            from unnest(%s::text[]) as s (site_id)
            cross join (values ('fast'), ('slow')) as l (lane)
            order by s.site_id, l.lane
            """,
            [site_ids],
        )
        return await cur.fetchall()


async def consecutive_failures(conn: AsyncConnection, site_id: str, lane: Lane) -> int:
    cur = await conn.execute(
        """
        select count(*) from pipeline_runs
        where site_id = %(site)s and lane = %(lane)s and status = 'failed'
          and started_at > coalesce(
              (select max(started_at) from pipeline_runs
               where site_id = %(site)s and lane = %(lane)s and status = 'success'),
              '-infinity')
        """,
        {"site": site_id, "lane": Lane(lane).value},
    )
    return (await cur.fetchone())[0]


async def recent_runs(
    conn: AsyncConnection,
    site_id: str | None = None,
    lane: Lane | None = None,
    limit: int = 50,
) -> list[dict]:
    lane_value = Lane(lane).value if lane else None
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select * from pipeline_runs
            where (%s::text is null or site_id = %s) and (%s::text is null or lane = %s)
            order by started_at desc, id
            limit %s
            """,
            [site_id, site_id, lane_value, lane_value, limit],
        )
        return await cur.fetchall()
