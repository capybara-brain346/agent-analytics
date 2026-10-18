import json
from datetime import timedelta

import pytest

from src.services.importer import import_due_files
from src.store import events, import_files
from src.store.inbox import ObjectNotFound  # noqa: F401
from tests.factories import NOW, make_import_file
from tests.fakes import MemoryInbox

CHROME = "Mozilla/5.0 Chrome/126"


def origin_line(sec=0, path="/pricing", ip="20.171.1.5", status=200, ua="GPTBot/1.2", rid="e1"):
    t = (NOW + timedelta(seconds=sec)).strftime("%d/%b/%Y:%H:%M:%S +0000")
    return f'{ip} - - [{t}] "GET {path} HTTP/1.1" {status} 100 "-" "{ua}" "{rid}" 0.010'


def cdn_record(sec=0, path="/pricing", status=403, rid="ray1", score=5):
    return json.dumps(
        {
            "request_id": rid,
            "timestamp": (NOW + timedelta(seconds=sec)).isoformat(),
            "client_ip": "20.171.1.5",
            "method": "GET",
            "path": path,
            "status": status,
            "bytes": 312,
            "user_agent": "GPTBot/1.2",
            "bot_score": score,
        }
    )


async def add_file(conn, inbox, lines, *, gz=False, source="origin", **o):
    n = len(inbox.objects)
    key = f"inbox/example/f{n}"
    sha, size = inbox.put_text(key, "\n".join(lines) + "\n", gzipped=gz)
    return await make_import_file(
        conn, object_key=key, sha256=sha, size_bytes=size, source=source, **o
    )


async def rows(conn, sql="select * from events order by line_no"):
    cur = await conn.execute(sql)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in await cur.fetchall()]


async def test_gzip_origin_file_end_to_end(conn):
    inbox = MemoryInbox()
    lines = [
        origin_line(0),
        "garbage line SECRET",
        origin_line(1, path="/docs", status=404),
        origin_line(0),  # duplicate of line 1
        origin_line(2, ip="2001:db8::1", ua=CHROME),
    ]
    f = await add_file(conn, inbox, lines, gz=True)
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts == {
        "files": 1, "files_failed": 0, "lines_total": 5, "lines_imported": 3,
        "lines_rejected": 1, "lines_duplicate": 1,
    }  # fmt: skip
    got = await import_files.get_file(conn, f["id"])
    assert got["status"] == "success"
    assert (got["lines_total"], got["lines_imported"]) == (5, 3)
    assert got["min_ts"] == NOW
    assert got["max_ts"] == NOW + timedelta(seconds=2)
    rejects = await import_files.list_rejects(conn, f["id"])
    assert [(r["line_no"], r["reason"]) for r in rejects] == [(2, "not a combined log line")]
    ev = await rows(conn)
    assert [e["line_no"] for e in ev] == [1, 3, 5]
    first = ev[0]
    assert first["source"] == "origin"
    assert first["status"] == first["origin_status"] == 200
    assert first["edge_status"] is None
    assert first["edge_request_id"] == "e1"
    assert first["response_time_ms"] == 10
    assert first["pair_state"] == "pending"  # example site pairs cdn + origin
    assert first["client_key"] and first["file_id"] == f["id"]
    assert first["verdict_id"] is None and first["cdn_bypass"] is False


async def test_cdn_file_maps_fields_and_edge_signal(conn):
    inbox = MemoryInbox()
    await add_file(
        conn, inbox, [cdn_record(0), cdn_record(1, rid="ray2", score=80), "{bad"], source="cdn"
    )
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["lines_imported"] == 2 and counts["lines_rejected"] == 1
    ev = await rows(conn)
    assert [e["edge_signal"] for e in ev] == ["bot", "human"]
    assert ev[0]["source"] == "cdn"
    assert ev[0]["status"] == ev[0]["edge_status"] == 403
    assert ev[0]["origin_status"] is None
    assert ev[0]["edge_request_id"] == "ray1"
    assert ev[0]["pair_state"] == "pending"


async def test_single_source_site_inserts_single(conn, config_dir, settings):
    (config_dir / "sites" / "solo.yaml").write_text(
        "site_id: solo\nsources: [origin]\nrequest_id_header: X-Request-ID\n"
    )
    inbox = MemoryInbox()
    await add_file(conn, inbox, [origin_line(0)], site_id="solo")
    await import_due_files(conn, "solo", inbox, now=NOW)
    ev = await rows(conn)
    assert ev[0]["pair_state"] == "single" and ev[0]["site_id"] == "solo"


async def test_duplicates_across_files_counted(conn):
    inbox = MemoryInbox()
    await add_file(conn, inbox, [origin_line(0), origin_line(1)])
    await import_due_files(conn, "example", inbox, now=NOW)
    f2 = await add_file(conn, inbox, [origin_line(1), origin_line(2)])
    await import_due_files(conn, "example", inbox, now=NOW)
    got = await import_files.get_file(conn, f2["id"])
    assert (got["lines_imported"], got["lines_duplicate"]) == (1, 1)
    assert await events.count_events(conn, "example") == 3


async def test_failed_file_does_not_stop_others(conn):
    inbox = MemoryInbox()
    missing = await make_import_file(conn, object_key="inbox/example/gone", received_at=NOW)
    ok = await add_file(conn, inbox, [origin_line(0)], received_at=NOW + timedelta(seconds=1))
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["files"] == 1 and counts["files_failed"] == 1
    bad = await import_files.get_file(conn, missing["id"])
    assert bad["status"] == "failed" and "gone" in bad["error"]
    assert (await import_files.get_file(conn, ok["id"]))["status"] == "success"


async def test_failed_file_rolls_back_partial_events(conn):
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [origin_line(0)])
    inbox.objects[f["object_key"]] = b"\x1f\x8b" + b"not really gzip"
    await import_due_files(conn, "example", inbox, now=NOW)
    assert (await import_files.get_file(conn, f["id"]))["status"] == "failed"
    assert await events.count_events(conn, "example") == 0


async def test_unknown_cdn_map_fails_file_only(conn, config_dir, settings):
    (config_dir / "sites" / "nomap.yaml").write_text("site_id: nomap\nsources: [cdn]\n")
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [cdn_record()], source="cdn", site_id="nomap")
    counts = await import_due_files(conn, "nomap", inbox, now=NOW)
    assert counts["files_failed"] == 1
    assert (await import_files.get_file(conn, f["id"]))["status"] == "failed"


async def test_live_before_backfill(conn):
    inbox = MemoryInbox()
    back = await add_file(conn, inbox, [origin_line(0)], priority="backfill", received_at=NOW)
    live = await add_file(
        conn, inbox, [origin_line(5)], priority="live", received_at=NOW + timedelta(minutes=1)
    )
    await import_due_files(conn, "example", inbox, now=NOW)
    a = await import_files.get_file(conn, back["id"])
    b = await import_files.get_file(conn, live["id"])
    assert b["started_at"] <= a["started_at"]
    assert a["status"] == b["status"] == "success"


async def test_work_limit_lines_stops_claiming(conn, settings, monkeypatch):
    monkeypatch.setattr(settings, "work_limit_lines", 2)
    inbox = MemoryInbox()
    for i in range(3):
        await add_file(conn, inbox, [origin_line(i * 10), origin_line(i * 10 + 1)])
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["files"] == 1
    assert await import_files.count_files(conn, "example", "new") == 2
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["files"] == 1


async def test_work_limit_bytes_stops_claiming(conn, settings, monkeypatch):
    monkeypatch.setattr(settings, "work_limit_bytes", 1)
    inbox = MemoryInbox()
    await add_file(conn, inbox, [origin_line(0)])
    await add_file(conn, inbox, [origin_line(1)])
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["files"] == 1


async def test_future_timestamp_rejected(conn):
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [origin_line(0), origin_line(86400 * 3)])
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert (counts["lines_imported"], counts["lines_rejected"]) == (1, 1)
    rej = await import_files.list_rejects(conn, f["id"])
    assert rej[0]["reason"] == "timestamp in the future"


async def test_force_reimport_replaces_events(conn):
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [origin_line(0), origin_line(1)])
    await import_due_files(conn, "example", inbox, now=NOW)
    assert await import_files.force_reimport(conn, f["id"])
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["lines_imported"] == 2 and counts["lines_duplicate"] == 0
    assert await events.count_events(conn, "example") == 2


async def test_large_file_batches(conn):
    inbox = MemoryInbox()
    lines = [origin_line(i % 3000, path=f"/p{i}", rid=f"r{i}") for i in range(12000)]
    await add_file(conn, inbox, lines)
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["lines_imported"] == 12000


async def test_no_files_returns_zero_counts(conn):
    counts = await import_due_files(conn, "example", MemoryInbox(), now=NOW)
    assert counts["files"] == 0
    with pytest.raises(Exception):  # noqa: B017
        await import_due_files(conn, "nosuchsite", MemoryInbox())


async def test_default_inbox_is_get_inbox(conn, monkeypatch):
    from src.services.importer import service

    inbox = MemoryInbox()
    await add_file(conn, inbox, [origin_line(0)])
    monkeypatch.setattr(service, "get_inbox", lambda: inbox)
    counts = await import_due_files(conn, "example")
    assert counts["lines_imported"] == 1


async def test_reimport_of_origin_file_skips_lines_already_merged(conn, config_dir):
    from src.services import pairing

    inbox = MemoryInbox()
    origin_file = await add_file(conn, inbox, [origin_line(0, rid="e1")], source="origin")
    await add_file(conn, inbox, [cdn_record(0, rid="e1", status=200)], source="cdn")
    await import_due_files(conn, "example", inbox, now=NOW)
    await pairing.pair_events(conn, "example", now=NOW)
    [paired] = await rows(conn)
    assert paired["source"] == "paired" and paired["origin_file_id"] == origin_file["id"]
    assert paired["origin_line_key"]

    assert await import_files.force_reimport(conn, origin_file["id"])
    counts = await import_due_files(conn, "example", inbox, now=NOW)
    assert counts["lines_imported"] == 0 and counts["lines_duplicate"] == 1
    [only] = await rows(conn)
    assert only["id"] == paired["id"]
