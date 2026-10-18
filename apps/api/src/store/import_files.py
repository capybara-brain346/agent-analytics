from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from src.models.domain import FilePriority, SourceType

# Rejects keep the line number and a short reason, never the line text (1.7).
MAX_REJECTS_PER_FILE = 10_000
MAX_REASON_CHARS = 200

type FileId = str | UUID


async def _one(conn: AsyncConnection, query: str, params: list) -> dict | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, params)
        return await cur.fetchone()


async def _all(conn: AsyncConnection, query: str, params: list) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(query, params)
        return await cur.fetchall()


async def insert_new(
    conn: AsyncConnection,
    site_id: str,
    source: SourceType | str,
    key: str,
    sha256: str,
    size: int,
    priority: FilePriority | str,
    entry: str = "ingest",
) -> str | None:
    cur = await conn.execute(
        """
        insert into import_files (site_id, source, object_key, sha256, size_bytes, priority, entry)
        values (%s, %s, %s, %s, %s, %s, %s)
        on conflict (site_id, sha256) do nothing
        returning id
        """,
        [site_id, str(source), key, sha256, size, str(priority), entry],
    )
    row = await cur.fetchone()
    return str(row[0]) if row else None


async def get_file(conn: AsyncConnection, file_id: FileId) -> dict | None:
    return await _one(conn, "select * from import_files where id = %s", [str(file_id)])


async def get_by_sha(conn: AsyncConnection, site_id: str, sha256: str) -> dict | None:
    return await _one(
        conn, "select * from import_files where site_id = %s and sha256 = %s", [site_id, sha256]
    )


_CAN_RESET = "status in ('success', 'failed', 'new') and object_deleted_at is null"


async def origin_partners(conn: AsyncConnection, site_id: str, cdn_file_id: FileId) -> list[str]:
    # Origin files whose lines sit in paired rows of this CDN file.
    rows = await _all(
        conn,
        "select distinct origin_file_id from events"
        " where site_id = %s and file_id = %s and origin_file_id is not null",
        [site_id, str(cdn_file_id)],
    )
    return [str(r["origin_file_id"]) for r in rows]


async def cdn_partners(conn: AsyncConnection, site_id: str, origin_file_id: FileId) -> list[str]:
    # CDN files whose paired rows hold lines of this origin file.
    rows = await _all(
        conn,
        "select distinct file_id from events where site_id = %s and origin_file_id = %s",
        [site_id, str(origin_file_id)],
    )
    return [str(r["file_id"]) for r in rows]


async def reset_files(conn: AsyncConnection, ids: list[str]) -> bool:
    # Back to 'new' so the importer reads the raw files again. All or none: when one file cannot
    # be read (importing, or its raw file was deleted), nothing changes and the answer is False.
    ok = await _all(conn, f"select id from import_files where id = any(%s) and {_CAN_RESET}", [ids])
    if len(ok) != len(set(ids)):
        return False
    await conn.execute(
        f"""
        update import_files
        set status = 'new', started_at = null, finished_at = null, error = null,
            lines_total = 0, lines_imported = 0, lines_rejected = 0, lines_duplicate = 0,
            lines_done = 0, retries = 0, min_ts = null, max_ts = null
        where id = any(%s) and {_CAN_RESET}
        """,
        [ids],
    )
    await conn.execute("delete from import_rejects where file_id = any(%s)", [ids])
    return True


async def force_reimport(conn: AsyncConnection, file_id: FileId) -> bool:
    # Decision 1.9. A CDN file can hold rows paired with origin lines; the origin row was deleted
    # at pairing. Those rows go with the file, so the origin files they came from are read again
    # too (all or none: when one of them cannot be read, nothing changes).
    file = await get_file(conn, file_id)
    if file is None:
        return False
    ids = [str(file_id)]
    if file["source"] == "cdn":
        ids += await origin_partners(conn, file["site_id"], file_id)
    if not await reset_files(conn, ids):
        return False
    if file["source"] == "cdn":
        await conn.execute(
            "delete from events where site_id = %s and file_id = %s", [file["site_id"], ids[0]]
        )
    return True


async def delete_file(conn: AsyncConnection, file_id: FileId) -> None:
    # The row goes (its rejects by cascade), so the same file can be uploaded again.
    await conn.execute("delete from import_files where id = %s", [str(file_id)])


async def claim_next_file(
    conn: AsyncConnection, site_id: str, allow_backfill: bool = True
) -> dict | None:
    # Live before backfill, then oldest first. SKIP LOCKED: two workers never take one file.
    # The status change lives in the caller's transaction, so a crash leaves the file "new".
    return await _one(
        conn,
        """
        update import_files f
        set status = 'importing', started_at = now(), attempts = f.attempts + 1
        where f.id = (
            select id from import_files
            where site_id = %s and status = 'new' and (%s or priority = 'live')
            order by (priority = 'live') desc, received_at, id
            limit 1
            for update skip locked
        )
        returning f.*
        """,
        [site_id, allow_backfill],
    )


async def mark_success(
    conn: AsyncConnection,
    file_id: FileId,
    counts: dict[str, int],
    min_ts: datetime | None,
    max_ts: datetime | None,
) -> None:
    await conn.execute(
        """
        update import_files
        set status = 'success', finished_at = now(), error = null,
            lines_total = %s, lines_imported = %s, lines_rejected = %s, lines_duplicate = %s,
            min_ts = %s, max_ts = %s
        where id = %s
        """,
        [
            counts.get("lines_total", 0),
            counts.get("lines_imported", 0),
            counts.get("lines_rejected", 0),
            counts.get("lines_duplicate", 0),
            min_ts,
            max_ts,
            str(file_id),
        ],
    )


async def mark_failed(conn: AsyncConnection, file_id: FileId, error: str) -> None:
    await conn.execute(
        "update import_files set status = 'failed', finished_at = now(), error = %s where id = %s",
        [error, str(file_id)],
    )


async def add_rejects(
    conn: AsyncConnection, file_id: FileId, rejects: Iterable[tuple[int, str]]
) -> int:
    row = await _one(
        conn,
        """
        select f.site_id, (select count(*) from import_rejects where file_id = f.id) as stored
        from import_files f where f.id = %s
        """,
        [str(file_id)],
    )
    if row is None:
        return 0
    room = max(MAX_REJECTS_PER_FILE - row["stored"], 0)
    rows = [
        (str(file_id), row["site_id"], line_no, reason[:MAX_REASON_CHARS])
        for line_no, reason in list(rejects)[:room]
    ]
    if rows:
        async with conn.cursor() as cur:
            await cur.executemany(
                "insert into import_rejects (file_id, site_id, line_no, reason)"
                " values (%s, %s, %s, %s)",
                rows,
            )
    return len(rows)


async def list_rejects(
    conn: AsyncConnection, file_id: FileId, limit: int = 100, offset: int = 0
) -> list[dict]:
    return await _all(
        conn,
        "select * from import_rejects where file_id = %s order by line_no, id limit %s offset %s",
        [str(file_id), limit, offset],
    )


def _filters(site_id: str | None, status: str | None) -> tuple[str, list]:
    where, params = [], []
    if site_id is not None:
        where.append("site_id = %s")
        params.append(site_id)
    if status is not None:
        where.append("status = %s")
        params.append(status)
    return (" where " + " and ".join(where)) if where else "", params


async def list_files(
    conn: AsyncConnection,
    site_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    where, params = _filters(site_id, status)
    return await _all(
        conn,
        f"select * from import_files{where} order by received_at desc, id limit %s offset %s",
        [*params, limit, offset],
    )


async def count_files(
    conn: AsyncConnection, site_id: str | None = None, status: str | None = None
) -> int:
    where, params = _filters(site_id, status)
    cur = await conn.execute(f"select count(*) from import_files{where}", params)
    return (await cur.fetchone())[0]


async def files_waiting(conn: AsyncConnection, site_id: str | None = None) -> int:
    cur = await conn.execute(
        "select count(*) from import_files"
        " where status = 'new' and (%s::text is null or site_id = %s)",
        [site_id, site_id],
    )
    return (await cur.fetchone())[0]


async def live_work_waiting(conn: AsyncConnection, site_id: str | None = None) -> bool:
    cur = await conn.execute(
        """
        select exists (
            select 1 from import_files
            where status = 'new' and priority = 'live' and (%s::text is null or site_id = %s)
        )
        """,
        [site_id, site_id],
    )
    return (await cur.fetchone())[0]


async def sites_with_new_files(conn: AsyncConnection) -> list[str]:
    cur = await conn.execute(
        "select distinct site_id from import_files where status = 'new' order by site_id"
    )
    return [row[0] for row in await cur.fetchall()]


async def expired_success_files(
    conn: AsyncConnection, retention_days: int, now: datetime | None = None
) -> list[dict]:
    return await _all(
        conn,
        """
        select * from import_files
        where status = 'success' and object_deleted_at is null
          and finished_at < coalesce(%s, now()) - make_interval(days => %s)
        order by finished_at
        """,
        [now, retention_days],
    )


async def mark_deleted(conn: AsyncConnection, file_id: FileId) -> None:
    # The row stays: its sha256 still blocks a second copy of the same chunk (S.6).
    await conn.execute(
        "update import_files set object_deleted_at = now() where id = %s", [str(file_id)]
    )


async def last_received_by_source(
    conn: AsyncConnection, site_id: str, live_only: bool = True
) -> dict[str, dict]:
    rows = await _all(
        conn,
        """
        select source, max(received_at) as last_file_at, max(max_ts) as last_event_at
        from import_files
        where site_id = %s and (not %s or priority = 'live')
        group by source
        """,
        [site_id, live_only],
    )
    return {r["source"]: {"last_file_at": r["last_file_at"], "last_event_at": r["last_event_at"]}
            for r in rows}  # fmt: skip


async def overlapping_files(conn: AsyncConnection, site_id: str, file_id: FileId) -> list[dict]:
    # Same site and same source only: a CDN file and an origin file overlap by design.
    return await _all(
        conn,
        """
        select o.* from import_files f
        join import_files o
          on o.site_id = f.site_id and o.source = f.source and o.id <> f.id
         and o.status = 'success' and o.min_ts is not null
         and o.min_ts <= f.max_ts and o.max_ts >= f.min_ts
        where f.id = %s and f.site_id = %s and f.min_ts is not null
        order by o.min_ts, o.id
        """,
        [str(file_id), site_id],
    )


async def save_progress(
    conn: AsyncConnection,
    file_id: FileId,
    lines_done: int,
    counts: dict[str, int],
    min_ts: datetime | None,
    max_ts: datetime | None,
) -> None:
    # The work limit stopped the file inside: keep the totals and the resume offset, and put the
    # file back in the queue (Flow 7.9).
    await conn.execute(
        """
        update import_files
        set status = 'new', lines_done = %s,
            lines_total = %s, lines_imported = %s, lines_rejected = %s, lines_duplicate = %s,
            min_ts = %s, max_ts = %s
        where id = %s
        """,
        [
            lines_done,
            counts["lines_total"],
            counts["lines_imported"],
            counts["lines_rejected"],
            counts["lines_duplicate"],
            min_ts,
            max_ts,
            str(file_id),
        ],
    )


async def release_file(
    conn: AsyncConnection, file_id: FileId, error: str, max_retries: int, count: bool = True
) -> bool:
    # A transient error (the inbox is down): the file goes back to 'new'. After max_retries it is
    # failed. Returns True when it is failed. count=False: the error is not the file's fault
    # (a lock wait), so the retry counter stays.
    step = 1 if count else 0
    row = await _one(
        conn,
        """
        update import_files
        set retries = retries + %s, error = %s,
            status = case when retries + %s >= %s then 'failed' else 'new' end,
            finished_at = case when retries + %s >= %s then now() else null end
        where id = %s
        returning status
        """,
        [step, error, step, max_retries, step, max_retries, str(file_id)],
    )
    return row is not None and row["status"] == "failed"


async def known_bucket_marks(conn: AsyncConnection, site_id: str, marks: list[str]) -> set[str]:
    cur = await conn.execute(
        "select mark from bucket_objects where site_id = %s and mark = any(%s)", [site_id, marks]
    )
    return {row[0] for row in await cur.fetchall()}


async def remember_bucket_mark(conn: AsyncConnection, site_id: str, mark: str) -> None:
    await conn.execute(
        "insert into bucket_objects (site_id, mark) values (%s, %s) on conflict do nothing",
        [site_id, mark],
    )


async def prune_bucket_marks(conn: AsyncConnection, older_than_days: int) -> int:
    cur = await conn.execute(
        "delete from bucket_objects where seen_at < now() - make_interval(days => %s)",
        [older_than_days],
    )
    return cur.rowcount
