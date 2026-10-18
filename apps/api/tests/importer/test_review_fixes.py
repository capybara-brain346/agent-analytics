import json
from datetime import timedelta

import psycopg
from botocore.exceptions import EndpointConnectionError

from src.services import pairing
from src.services.importer import import_due_files
from src.services.importer.bucket_reader import BucketReader
from src.store import events, import_files
from tests.factories import NOW
from tests.fakes import MemoryInbox
from tests.importer.test_bucket_reader import TARGET, FakeBucketInbox
from tests.importer.test_importer import add_file, cdn_record, origin_line, rows


async def test_late_origin_file_still_pairs_with_old_cdn_rows(conn, config_dir):
    inbox = MemoryInbox()
    await add_file(conn, inbox, [cdn_record(-2400, rid="e1", status=200)], source="cdn")
    await import_due_files(conn, "example", inbox, now=NOW)
    first = await pairing.pair_events(conn, "example", now=NOW)
    assert first["single"] == 0
    await add_file(conn, inbox, [origin_line(-2400, rid="e1")], source="origin")
    later = NOW + timedelta(minutes=1)
    await import_due_files(conn, "example", inbox, now=later)
    second = await pairing.pair_events(conn, "example", now=later)
    assert second["paired"] == 1
    assert len(await rows(conn)) == 1


async def test_pending_row_expires_after_wait_from_arrival(conn, config_dir):
    inbox = MemoryInbox()
    await add_file(conn, inbox, [cdn_record(-2400, rid="e1")], source="cdn")
    await import_due_files(conn, "example", inbox, now=NOW)
    result = await pairing.pair_events(conn, "example", now=NOW + timedelta(minutes=11))
    assert result["single"] == 1


async def test_bad_values_become_rejects_not_step_failures(conn, config_dir):
    inbox = MemoryInbox()
    bad_ua = json.loads(cdn_record(0, rid="a"))
    bad_ua["user_agent"] = "evil\u0000ua"
    bad_path = json.loads(cdn_record(1, rid="b"))
    bad_path["path"] = "/x\ud800"
    bad_bytes = json.loads(cdn_record(2, rid="c"))
    bad_bytes["bytes"] = 10**30
    lines = [json.dumps(r) for r in (bad_ua, bad_path, bad_bytes)] + [cdn_record(3, rid="d")]
    await add_file(conn, inbox, lines, source="cdn")
    big_time = origin_line(4).replace(" 0.010", " 5000000.0")
    await add_file(conn, inbox, [big_time, origin_line(5, rid="z")])
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["files_failed"] == 0
    assert counts["lines_imported"] == 2
    assert counts["lines_rejected"] == 4


async def test_data_error_fails_file_only(conn, config_dir, monkeypatch):
    inbox = MemoryInbox()
    await add_file(conn, inbox, [origin_line(0)])
    real = events.copy_events

    async def boom(c, rws, **kw):
        raise psycopg.errors.DataError("bad")

    monkeypatch.setattr(events, "copy_events", boom)
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["files_failed"] == 1
    monkeypatch.setattr(events, "copy_events", real)


async def test_partition_is_created_outside_the_caller_transaction(conn, db_url):
    day = NOW + timedelta(days=40)
    row = (
        "example", day, None, 1, "origin", "GET", None, "/p", 200, None, 200, 10, None, None,
        "20.171.1.5", "UA", "ck", None, None, "none", "k1", "single", False,
    )  # fmt: skip
    async with conn.transaction():
        assert await events.copy_events(conn, [row]) == 1
        async with await psycopg.AsyncConnection.connect(db_url, autocommit=True) as other:
            await other.execute("set lock_timeout = '500ms'")
            async with other.transaction():
                await other.execute("lock table events in access share mode")


async def test_cdn_chunk_sent_again_after_pairing_is_duplicate(conn, config_dir):
    inbox = MemoryInbox()
    await add_file(conn, inbox, [cdn_record(0, rid="e1", status=200)], source="cdn")
    await add_file(conn, inbox, [origin_line(0, rid="e1")], source="origin")
    await import_due_files(conn, "example", inbox, now=NOW)
    assert (await pairing.pair_events(conn, "example", now=NOW))["paired"] == 1
    await add_file(conn, inbox, [cdn_record(0, rid="e1", status=200), ""], source="cdn")
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["lines_imported"] == 0 and counts["lines_duplicate"] == 1
    assert len(await rows(conn)) == 1


async def test_force_reimport_of_paired_cdn_file_keeps_origin_half(conn, config_dir):
    inbox = MemoryInbox()
    cdn_file = await add_file(conn, inbox, [cdn_record(0, rid="e1", status=200)], source="cdn")
    await add_file(conn, inbox, [origin_line(0, rid="e1", status=500)], source="origin")
    await import_due_files(conn, "example", inbox, now=NOW)
    await pairing.pair_events(conn, "example", now=NOW)
    assert await import_files.force_reimport(conn, cdn_file["id"])
    await import_due_files(conn, "example", inbox, now=NOW)
    result = await pairing.pair_events(conn, "example", now=NOW)
    assert result["paired"] == 1
    [row] = await rows(conn)
    assert row["origin_status"] == 500 and row["source"] == "paired"


class FlakyInbox(MemoryInbox):
    def __init__(self, error: Exception):
        super().__init__()
        self.error = error

    async def open_lines(self, key):
        raise self.error
        yield ""


async def test_transient_inbox_error_leaves_file_retryable(conn, config_dir):
    inbox = FlakyInbox(EndpointConnectionError(endpoint_url="http://s3"))
    f = await add_file(conn, inbox, [origin_line(0)])
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["files_failed"] == 0
    assert (await import_files.get_file(conn, f["id"]))["status"] == "new"
    for _ in range(10):
        await import_due_files(conn, "example", inbox, now=NOW)
    assert (await import_files.get_file(conn, f["id"]))["status"] == "failed"


async def test_missing_object_fails_file(conn, config_dir):
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [origin_line(0)])
    inbox.objects.clear()
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["files_failed"] == 1
    assert (await import_files.get_file(conn, f["id"]))["status"] == "failed"


async def test_work_limit_applies_inside_one_file(config_dir, conn, settings, monkeypatch):
    monkeypatch.setattr(settings, "work_limit_lines", 2)
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [origin_line(i, path=f"/p{i}") for i in range(5)])
    await import_due_files(conn, "example", inbox, now=NOW)
    mid = await import_files.get_file(conn, f["id"])
    assert mid["status"] == "new" and mid["lines_done"] == 2 and mid["lines_imported"] == 2
    for _ in range(2):
        await import_due_files(conn, "example", inbox, now=NOW)
    done = await import_files.get_file(conn, f["id"])
    assert done["status"] == "success"
    assert (done["lines_total"], done["lines_imported"]) == (5, 5)
    assert len(await rows(conn)) == 5


async def test_bucket_reader_does_not_copy_known_objects_after_restart(conn, settings):
    inbox = FakeBucketInbox({"logs/a.json": (b"line a\n", NOW)})
    await BucketReader(inbox).read_new(conn, TARGET, now=NOW)
    copies = []
    again = FakeBucketInbox(inbox.source)
    real = again.copy_from

    async def counting(*a, **k):
        copies.append(a)
        return await real(*a, **k)

    again.copy_from = counting
    counts = await BucketReader(again).read_new(conn, TARGET, now=NOW)
    assert copies == [] and counts["objects_skipped"] == 1
