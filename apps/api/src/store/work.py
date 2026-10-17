from datetime import datetime, timedelta

from psycopg import AsyncConnection

from src.models.domain import Lane

DEFAULT_SLOW_INTERVAL = timedelta(hours=6)
SLOW_RETRY_AFTER = timedelta(minutes=15)


async def ensure_site_work(conn: AsyncConnection, site_ids: list[str]) -> None:
    for site_id in site_ids:
        for lane in Lane:
            await conn.execute(
                "insert into site_work (site_id, lane) values (%s, %s) on conflict do nothing",
                [site_id, lane.value],
            )


# Take = claim: the row is stamped in the same statement, so a second worker cannot take it
# again and the same tick does not see the site as due a second time.
_FAST_DUE = "last_run_at is null or last_run_at < %(now)s"
_SLOW_DUE = "next_due_at is null or next_due_at <= %(now)s"

_TAKE = """
    update site_work
    set last_run_at = %(now)s,
        next_due_at = case when lane = 'slow' then %(next_due)s else next_due_at end
    where (site_id, lane) in (
        select site_id, lane from site_work
        where lane = %(lane)s and ({due})
          and (%(ids)s::text[] is null or site_id = any(%(ids)s))
        order by last_run_at nulls first, site_id
        for update skip locked limit 1
    )
    returning site_id
"""


async def take_due_site(
    conn: AsyncConnection,
    lane: Lane,
    now: datetime,
    site_ids: list[str] | None = None,
    slow_interval: timedelta = DEFAULT_SLOW_INTERVAL,
) -> str | None:
    lane = Lane(lane)
    # Fast lane: every configured site is due once each tick (cheap: an idle run is a few
    # empty queries). Slow lane: due when next_due_at has passed.
    due = _FAST_DUE if lane == Lane.FAST else _SLOW_DUE
    cur = await conn.execute(
        _TAKE.format(due=due),
        {"lane": lane.value, "now": now, "ids": site_ids, "next_due": now + slow_interval},
    )
    row = await cur.fetchone()
    return row[0] if row else None


async def record_run(conn: AsyncConnection, site_id: str, lane: Lane, success: bool) -> None:
    lane = Lane(lane)
    retry = SLOW_RETRY_AFTER if lane == Lane.SLOW and not success else None
    await conn.execute(
        """
        insert into site_work as w
            (site_id, lane, last_run_at, last_success_at, consecutive_failures, next_due_at)
        values (%(site)s, %(lane)s, now(), case when %(ok)s then now() end,
                case when %(ok)s then 0 else 1 end, now() + %(retry)s)
        on conflict (site_id, lane) do update set
            last_run_at = greatest(w.last_run_at, now()),
            last_success_at = case when %(ok)s then now() else w.last_success_at end,
            consecutive_failures = case when %(ok)s then 0 else w.consecutive_failures + 1 end,
            next_due_at = case when %(retry)s::interval is not null
                then now() + %(retry)s else w.next_due_at end
        """,
        {"site": site_id, "lane": lane.value, "ok": success, "retry": retry},
    )


LOCK_SKIP_RETRY = timedelta(minutes=5)


async def release_slow(conn: AsyncConnection, site_id: str, now: datetime) -> None:
    # The slow lock was taken, so nothing ran: undo the 'next_due_at = now + interval' of the take
    # and try again soon, not after a full window.
    await conn.execute(
        "update site_work set next_due_at = %s where site_id = %s and lane = 'slow'",
        [now + LOCK_SKIP_RETRY, site_id],
    )
