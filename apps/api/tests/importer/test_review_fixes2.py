import asyncio
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg import AsyncConnection

from src.config import get_settings
from src.services import cleanup, pairing
from src.services.importer import import_due_files
from src.services.importer import service as imp
from src.services.importer.bucket_reader import BucketReader
from src.store import events, import_files, locks
from tests.factories import NOW, make_event, make_import_file
from tests.fakes import MemoryInbox
from tests.importer.test_bucket_reader import TARGET, FakeBucketInbox
from tests.importer.test_importer import add_file, cdn_record, origin_line, rows

DAY = 86400


# ---- 1: a partition is made without ACCESS EXCLUSIVE on events ----


async def test_multiday_file_with_small_batches_imports(conn, config_dir, monkeypatch):
    monkeypatch.setattr(imp, "BATCH_ROWS", 1)
    inbox = MemoryInbox()
    f = await add_file(
        conn,
        inbox,
        [origin_line(-20 * DAY, rid="a"), origin_line(-19 * DAY, rid="b")],
        priority="backfill",
    )
    async with conn.transaction():
        await import_due_files(conn, "example", inbox, now=NOW)
    got = await import_files.get_file(conn, f["id"])
    assert (got["status"], got["retries"], got["lines_imported"]) == ("success", 0, 2)
    assert len(await rows(conn)) == 2


async def test_partition_is_made_while_another_writer_is_open(conn, config_dir, db_url):
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [origin_line(-25 * DAY, rid="old")], priority="backfill")
    async with await AsyncConnection.connect(db_url) as other:
        # An open import step of another worker: ROW EXCLUSIVE on events.
        await make_event(conn, ts=NOW)
        await other.execute(
            "insert into events (site_id, ts, source, path, line_key) "
            "values ('x', %s, 'origin', '/', 'k')",
            [NOW],
        )
        async with conn.transaction():
            await import_due_files(conn, "example", inbox, now=NOW)
        await other.rollback()
    assert (await import_files.get_file(conn, f["id"]))["status"] == "success"


async def test_new_partition_has_the_indexes_of_events(conn):
    await events.ensure_partitions(conn, [datetime(2026, 3, 3, tzinfo=UTC).date()])
    cur = await conn.execute(
        "select (select count(*) from pg_indexes where tablename = 'events_20260303'), "
        "(select count(*) from pg_index where indrelid = 'events'::regclass)"
    )
    in_partition, in_parent = await cur.fetchone()
    assert in_partition == in_parent
    cur = await conn.execute(
        "select count(*) from pg_inherits where inhrelid = 'events_20260303'::regclass"
    )
    assert (await cur.fetchone())[0] == 1


async def test_lock_timeout_does_not_count_as_retry(conn, config_dir, monkeypatch):
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [origin_line(0)])

    async def busy(c, days):
        raise psycopg.errors.LockNotAvailable("busy")

    monkeypatch.setattr(events, "ensure_partitions", busy)
    # Partition call at the start of the step must not fail the step.
    async with conn.transaction():
        await import_due_files(conn, "example", inbox, now=NOW)
    # Now only the call in copy_events fails.
    calls = []
    real = events.ensure_partitions

    async def only_copy(c, days):
        calls.append(1)
        if len(calls) > 1:
            raise psycopg.errors.LockNotAvailable("busy")
        return await real(c, days)

    monkeypatch.setattr(events, "ensure_partitions", only_copy)
    for _ in range(imp.MAX_RETRIES + 2):
        calls.clear()
        async with conn.transaction():
            await import_due_files(conn, "example", inbox, now=NOW)
    got = await import_files.get_file(conn, f["id"])
    assert got["status"] == "new" and got["retries"] == 0


# ---- 3: a pending row waits while the other source still has queued files ----


async def pending(conn, source, age_min):
    ts = NOW - timedelta(minutes=age_min)
    return await make_event(
        conn, source=source, pair_state="pending", edge_request_id="r", ts=ts, imported_at=ts
    )


async def test_pending_row_waits_for_queued_file_of_other_source(conn, config_dir):
    await pending(conn, "cdn", 30)
    queued = await make_import_file(conn, source="origin", status="new", priority="backfill")
    r = await pairing.pair_events(conn, "example", now=NOW)
    assert r["single"] == 0
    await import_files.mark_success(conn, queued["id"], {}, None, None)
    r = await pairing.pair_events(conn, "example", now=NOW)
    assert r["single"] == 1


async def test_queued_file_of_same_source_does_not_hold_rows(conn, config_dir):
    await pending(conn, "cdn", 30)
    await make_import_file(conn, source="cdn", status="new")
    assert (await pairing.pair_events(conn, "example", now=NOW))["single"] == 1


async def test_hard_limit_expires_rows_even_with_queued_files(conn, config_dir):
    settings = get_settings()
    await pending(conn, "origin", settings.pair_hard_limit_hours * 60 + 5)
    await make_import_file(conn, source="cdn", status="importing")
    r = await pairing.pair_events(conn, "example", now=NOW)
    assert (r["single"], r["cdn_bypass"]) == (1, 1)


async def test_sliced_backfill_of_both_sources_pairs(conn, config_dir, monkeypatch):
    monkeypatch.setenv("WORK_LIMIT_LINES", "1")
    get_settings.cache_clear()
    inbox = MemoryInbox()
    n = 12
    await add_file(
        conn,
        inbox,
        [cdn_record(-3600 + i, rid=f"r{i}", status=200) for i in range(n)],
        source="cdn",
        priority="backfill",
    )
    await add_file(
        conn, inbox, [origin_line(-3600 + i, rid=f"r{i}") for i in range(n)], priority="backfill"
    )
    tot = {"paired": 0, "single": 0, "cdn_bypass": 0}
    for t in range(2 * n + 12):
        now = NOW + timedelta(minutes=t)
        async with conn.transaction():
            await import_due_files(conn, "example", inbox, now=now)
        async with conn.transaction():
            c = await pairing.pair_events(conn, "example", now=now)
        for k in tot:
            tot[k] += c[k]
    assert tot == {"paired": n, "single": 0, "cdn_bypass": 0}
    assert len(await rows(conn)) == n


# ---- 5: partitions are detached without a long ACCESS EXCLUSIVE lock ----


async def exists(conn, name):
    cur = await conn.execute("select to_regclass(%s) is not null", [name])
    return (await cur.fetchone())[0]


def part_name(ts):
    return f"events_{ts.strftime('%Y%m%d')}"


async def test_old_partition_is_detached_and_dropped(conn):
    old = datetime.now(UTC) - timedelta(days=60)
    await make_event(conn, ts=old)
    await make_event(conn, ts=datetime.now(UTC))
    assert await cleanup.drop_expired_partitions(keep_days=30) >= 1
    assert not await exists(conn, part_name(old))
    cur = await conn.execute("select count(*) from events")
    assert (await cur.fetchone())[0] == 1


async def test_cleanup_finishes_an_interrupted_detach(conn):
    old = datetime.now(UTC) - timedelta(days=60)
    await make_event(conn, ts=old)
    # Interrupted after the detach: the table is left alone, not attached.
    await conn.execute(f"alter table events detach partition {part_name(old)} concurrently")
    assert await cleanup.drop_expired_partitions(keep_days=30) >= 1
    assert not await exists(conn, part_name(old))


async def test_cleanup_gives_up_when_a_writer_holds_the_partition(conn, db_url, monkeypatch):
    old = datetime.now(UTC) - timedelta(days=60)
    await make_event(conn, ts=old)
    monkeypatch.setattr(events, "DETACH_LOCK_TIMEOUT", "300ms")
    async with await AsyncConnection.connect(db_url) as other:
        await other.execute(
            "insert into events (site_id, ts, source, path, line_key) "
            "values ('x', %s, 'origin', '/', 'k2')",
            [old],
        )
        started = asyncio.get_running_loop().time()
        await cleanup.drop_expired_partitions(keep_days=30)
        assert asyncio.get_running_loop().time() - started < 5
        assert await exists(conn, part_name(old))
        await other.rollback()
    await cleanup.drop_expired_partitions(keep_days=30)
    assert not await exists(conn, part_name(old))


# ---- 7: bucket reader commits per object and takes a lock per target ----


class FailingSecond(FakeBucketInbox):
    async def copy_from(self, bucket, key, dest_key=None):
        if key.endswith("b.json"):
            raise OSError("s3 down")
        return await super().copy_from(bucket, key, dest_key)


async def test_bucket_objects_before_a_failure_are_kept(db_url, clean_db, settings):
    inbox = FailingSecond({"logs/a.json": (b"line a\n", NOW), "logs/b.json": (b"line b\n", NOW)})
    async with await AsyncConnection.connect(db_url) as c:  # not autocommit, like the pool
        with pytest.raises(OSError):
            await BucketReader(inbox).read_new(c, TARGET, now=NOW)
    async with await AsyncConnection.connect(db_url, autocommit=True) as check:
        files = await import_files.list_files(check, "example")
        assert len(files) == 1
        again = FakeBucketInbox({"logs/a.json": (b"line a\n", NOW)})
        counts = await BucketReader(again).read_new(check, TARGET, now=NOW)
        assert counts["objects_new"] == 0 and len(again.objects) == 0


async def test_bucket_target_is_read_by_one_worker(conn, db_url, settings):
    inbox = FakeBucketInbox({"logs/a.json": (b"line a\n", NOW)})
    async with await AsyncConnection.connect(db_url, autocommit=True) as other:
        async with locks.advisory_lock(
            other, locks.bucket_lock_key("example", "cdn-logs", "logs/")
        ) as got:
            assert got
            counts = await BucketReader(inbox).read_new(conn, TARGET, now=NOW)
            assert counts["objects_new"] == 0 and not inbox.objects
    counts = await BucketReader(inbox).read_new(conn, TARGET, now=NOW)
    assert counts["objects_new"] == 1


# ---- 8: slices of one file grow, so a large file is not read n times ----


class CountingInbox(MemoryInbox):
    def __init__(self):
        super().__init__()
        self.read = 0

    async def open_lines(self, key):
        async for line in super().open_lines(key):
            self.read += 1
            yield line


async def test_slices_grow_so_large_file_is_read_few_times(conn, config_dir, monkeypatch):
    monkeypatch.setenv("WORK_LIMIT_LINES", "2")
    get_settings.cache_clear()
    inbox = CountingInbox()
    n = 60
    f = await add_file(conn, inbox, [origin_line(i, rid=f"r{i}") for i in range(n)], gz=True)
    ticks = 0
    while (await import_files.get_file(conn, f["id"]))["status"] != "success":
        ticks += 1
        assert ticks < 40
        async with conn.transaction():
            await import_due_files(conn, "example", inbox, now=NOW)
    assert len(await rows(conn)) == n
    assert inbox.read < 4 * n  # fixed slices of 2 lines would read about n * n / 4 lines
