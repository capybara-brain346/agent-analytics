import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

import psycopg
from psycopg import AsyncConnection

from src.config import get_settings

# Column order of the row tuples that copy_events takes.
EVENT_COLUMNS = (
    "site_id",
    "ts",
    "file_id",
    "line_no",
    "source",
    "method",
    "host",
    "path",
    "status",
    "edge_status",
    "origin_status",
    "bytes_sent",
    "response_time_ms",
    "referrer",
    "client_ip",
    "user_agent",
    "client_key",
    "request_id",
    "edge_request_id",
    "edge_signal",
    "line_key",
    "pair_state",
    "cdn_bypass",
)
_COLUMNS_SQL = ", ".join(EVENT_COLUMNS)
_TS = EVENT_COLUMNS.index("ts")


PARTITION_LOCK_TIMEOUT = "2s"
DETACH_LOCK_TIMEOUT = "5s"
DETACH_STATEMENT_TIMEOUT = "60s"


async def _own_connection() -> AsyncConnection:
    return await AsyncConnection.connect(
        get_settings().database_url, autocommit=True, options="-c TimeZone=UTC"
    )


async def ensure_partitions(conn: AsyncConnection, days: Iterable[date]) -> None:
    # A missing partition is made by ensure_events_partition on its own autocommit connection, so
    # it is visible at once and the import transaction holds no lock for it. The function makes a
    # standalone table and ATTACHes it: that takes only SHARE UPDATE EXCLUSIVE on events, which
    # does not wait for open writers (CREATE ... PARTITION OF would wait for our own step).
    missing = []
    for day in sorted(set(days)):
        cur = await conn.execute(
            "select not exists (select 1 from pg_inherits where inhparent = 'events'::regclass "
            "and inhrelid = to_regclass(%s))",
            [f"events_{day.strftime('%Y%m%d')}"],
        )
        if (await cur.fetchone())[0]:
            missing.append(day)
    if not missing:
        return
    async with await _own_connection() as own:
        await own.execute(f"set lock_timeout = '{PARTITION_LOCK_TIMEOUT}'")
        for day in missing:
            await own.execute("select ensure_events_partition(%s)", [day])


async def copy_events(
    conn: AsyncConnection, rows: Iterable[tuple], imported_at: datetime | None = None
) -> int:
    # Bulk insert. Returns the number of rows inserted; rows that hit the dedupe index are skipped.
    # imported_at = arrival time of the rows; the pair wait (1b.6) counts from it.
    rows = list(rows)
    if not rows:
        return 0
    await ensure_partitions(conn, {row[_TS].astimezone(UTC).date() for row in rows})
    await conn.execute(
        f"create temp table if not exists events_stage as select {_COLUMNS_SQL} "
        "from events with no data"
    )
    await conn.execute("truncate events_stage")
    async with conn.cursor() as cur:
        async with cur.copy(f"copy events_stage ({_COLUMNS_SQL}) from stdin") as copy:
            for row in rows:
                await copy.write_row(row)
        await cur.execute(
            f"insert into events ({_COLUMNS_SQL}, imported_at) "
            f"select {_COLUMNS_SQL}, coalesce(%s, now()) from events_stage s "
            # A line that is already counted in a paired row is a duplicate: an origin line by its
            # origin_line_key, a CDN line by the line_key the paired row kept (1b, 1.8).
            "where not (s.source = 'origin' and exists ("
            "select 1 from events p where p.site_id = s.site_id "
            "and p.origin_line_key = s.line_key "
            "and p.ts between s.ts - interval '1 hour' and s.ts + interval '1 hour')) "
            "and not (s.source = 'cdn' and exists ("
            "select 1 from events p where p.site_id = s.site_id and p.source = 'paired' "
            "and p.line_key = s.line_key and p.ts = s.ts)) "
            "on conflict (site_id, source, line_key, ts) do nothing",
            [imported_at],
        )
        inserted = cur.rowcount
    await conn.execute("truncate events_stage")
    return inserted


async def delete_file_events(conn: AsyncConnection, site_id: str, file_id: str) -> int:
    cur = await conn.execute(
        "delete from events where site_id = %s and file_id = %s", [site_id, str(file_id)]
    )
    return cur.rowcount


async def delete_file_rows(conn: AsyncConnection, site_id: str, file_id: str) -> int:
    # Every row that holds a line of the file: its own rows, and the paired rows that keep one of
    # its origin lines (the origin row itself was deleted at pairing).
    cur = await conn.execute(
        "delete from events where site_id = %s and (file_id = %s or origin_file_id = %s)",
        [site_id, str(file_id), str(file_id)],
    )
    return cur.rowcount


_PARTITION_DAY = re.compile(r"^events_(\d{8})$")


async def drop_old_partitions(keep_days: int) -> int:
    # Retention. DROP of an attached partition takes ACCESS EXCLUSIVE on events: it would wait
    # behind every open import step, and all queries would wait behind it. Instead each old
    # partition is detached CONCURRENTLY (no lock that blocks readers and writers; not allowed in
    # a transaction, so on an own autocommit connection) and then dropped as a plain table. A
    # lock timeout leaves the partition for the next run. An interrupted detach stays "pending"
    # in pg_inherits: the next run finishes it (FINALIZE). A table that was detached but not yet
    # dropped is dropped.
    cutoff = datetime.now(UTC).date() - timedelta(days=keep_days)
    dropped = 0
    async with await _own_connection() as own:
        await own.execute(f"set lock_timeout = '{DETACH_LOCK_TIMEOUT}'")
        await own.execute(f"set statement_timeout = '{DETACH_STATEMENT_TIMEOUT}'")
        cur = await own.execute(
            """
            select c.relname, c.relispartition, coalesce(i.inhdetachpending, false)
            from pg_class c
            left join pg_inherits i on i.inhrelid = c.oid and i.inhparent = 'events'::regclass
            where c.relnamespace = 'public'::regnamespace and c.relkind = 'r'
              and c.relname ~ '^events_[0-9]{8}$'
              and (i.inhrelid is not null or not c.relispartition)
            order by c.relname
            """
        )
        for name, attached, pending in await cur.fetchall():
            day = datetime.strptime(_PARTITION_DAY.match(name).group(1), "%Y%m%d").date()
            if day >= cutoff:
                continue
            try:
                if attached:
                    mode = "finalize" if pending else "concurrently"
                    await own.execute(f"alter table events detach partition {name} {mode}")
                await own.execute(f"drop table {name}")
            except psycopg.errors.QueryCanceled, psycopg.errors.LockNotAvailable:
                continue
            dropped += 1
    return dropped


async def count_events(conn: AsyncConnection, site_id: str) -> int:
    cur = await conn.execute("select count(*) from events where site_id = %s", [site_id])
    return (await cur.fetchone())[0]
