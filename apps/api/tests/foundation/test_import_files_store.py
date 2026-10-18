from datetime import timedelta

from psycopg import AsyncConnection

from src.models.domain import FilePriority
from src.store import import_files
from tests.factories import NOW, make_import_file


async def insert(conn: AsyncConnection, sha: str = "a" * 64, **kw) -> str | None:
    args = {
        "site_id": "example",
        "source": "origin",
        "key": f"k-{sha[:4]}",
        "sha256": sha,
        "size": 10,
        "priority": FilePriority.LIVE,
    } | kw
    return await import_files.insert_new(
        conn, args["site_id"], args["source"], args["key"], args["sha256"], args["size"],
        args["priority"], entry=args.get("entry", "ingest"),
    )  # fmt: skip


async def test_insert_new_returns_id_then_none_on_duplicate_sha(conn: AsyncConnection) -> None:
    first = await insert(conn)
    assert first
    assert await insert(conn, key="other") is None


async def test_same_sha_other_site_is_not_duplicate(conn: AsyncConnection) -> None:
    assert await insert(conn, site_id="a")
    assert await insert(conn, site_id="b")


async def test_insert_new_sets_new_status(conn: AsyncConnection) -> None:
    file_id = await insert(conn, priority=FilePriority.BACKFILL, entry="upload")
    row = await import_files.get_file(conn, file_id)
    assert row["status"] == "new"
    assert row["priority"] == "backfill"
    assert row["entry"] == "upload"
    assert row["attempts"] == 0


async def test_claim_live_before_backfill_then_oldest(conn: AsyncConnection) -> None:
    await make_import_file(conn, priority="backfill", received_at=NOW - timedelta(hours=3))
    old_live = await make_import_file(conn, received_at=NOW - timedelta(hours=2))
    new_live = await make_import_file(conn, received_at=NOW - timedelta(hours=1))
    first = await import_files.claim_next_file(conn, "example")
    second = await import_files.claim_next_file(conn, "example")
    third = await import_files.claim_next_file(conn, "example")
    assert first["id"] == old_live["id"]
    assert second["id"] == new_live["id"]
    assert third["priority"] == "backfill"
    assert await import_files.claim_next_file(conn, "example") is None


async def test_claim_sets_importing_and_attempts(conn: AsyncConnection) -> None:
    await make_import_file(conn)
    row = await import_files.claim_next_file(conn, "example")
    assert row["status"] == "importing"
    assert row["attempts"] == 1
    assert row["started_at"] is not None


async def test_claim_only_own_site(conn: AsyncConnection) -> None:
    await make_import_file(conn, site_id="other")
    assert await import_files.claim_next_file(conn, "example") is None


async def test_claim_can_skip_backfill(conn: AsyncConnection) -> None:
    await make_import_file(conn, priority="backfill")
    assert await import_files.claim_next_file(conn, "example", allow_backfill=False) is None
    assert await import_files.claim_next_file(conn, "example") is not None


async def test_claim_skip_locked(conn: AsyncConnection, db_url: str) -> None:
    await make_import_file(conn)
    async with (
        await AsyncConnection.connect(db_url) as a,
        await AsyncConnection.connect(db_url) as b,
    ):
        first = await import_files.claim_next_file(a, "example")
        second = await import_files.claim_next_file(b, "example")
        assert first is not None
        assert second is None


async def test_mark_success(conn: AsyncConnection) -> None:
    row = await make_import_file(conn, status="importing")
    counts = {"lines_total": 10, "lines_imported": 7, "lines_rejected": 2, "lines_duplicate": 1}
    await import_files.mark_success(conn, row["id"], counts, NOW - timedelta(hours=1), NOW)
    got = await import_files.get_file(conn, row["id"])
    assert got["status"] == "success"
    assert got["lines_imported"] == 7
    assert got["lines_duplicate"] == 1
    assert got["min_ts"] == NOW - timedelta(hours=1)
    assert got["max_ts"] == NOW
    assert got["finished_at"] is not None
    assert got["error"] is None


async def test_mark_failed(conn: AsyncConnection) -> None:
    row = await make_import_file(conn, status="importing")
    await import_files.mark_failed(conn, row["id"], "bad gzip")
    got = await import_files.get_file(conn, row["id"])
    assert (got["status"], got["error"]) == ("failed", "bad gzip")
    assert got["finished_at"] is not None


async def test_add_rejects_and_list(conn: AsyncConnection) -> None:
    row = await make_import_file(conn)
    added = await import_files.add_rejects(conn, row["id"], [(3, "bad time"), (9, "bad status")])
    assert added == 2
    rejects = await import_files.list_rejects(conn, row["id"])
    assert [(r["line_no"], r["reason"]) for r in rejects] == [(3, "bad time"), (9, "bad status")]
    assert rejects[0]["site_id"] == "example"


async def test_add_rejects_truncates_reason_and_caps_count(
    conn: AsyncConnection, monkeypatch
) -> None:
    monkeypatch.setattr(import_files, "MAX_REJECTS_PER_FILE", 2)
    row = await make_import_file(conn)
    added = await import_files.add_rejects(conn, row["id"], [(1, "x" * 500), (2, "b"), (3, "c")])
    assert added == 2
    rejects = await import_files.list_rejects(conn, row["id"])
    assert len(rejects[0]["reason"]) <= import_files.MAX_REASON_CHARS


async def test_force_reimport_resets_row(conn: AsyncConnection) -> None:
    row = await make_import_file(conn, status="success", lines_total=5, lines_imported=5)
    await import_files.add_rejects(conn, row["id"], [(1, "r")])
    assert await import_files.force_reimport(conn, row["id"]) is True
    got = await import_files.get_file(conn, row["id"])
    assert got["status"] == "new"
    assert got["lines_total"] == 0
    assert got["finished_at"] is None
    assert got["min_ts"] is None
    assert await import_files.list_rejects(conn, row["id"]) == []


async def test_force_reimport_refuses_running_or_deleted(conn: AsyncConnection) -> None:
    running = await make_import_file(conn, status="importing")
    deleted = await make_import_file(conn, status="success", object_deleted_at=NOW)
    assert await import_files.force_reimport(conn, running["id"]) is False
    assert await import_files.force_reimport(conn, deleted["id"]) is False


async def test_get_by_sha(conn: AsyncConnection) -> None:
    row = await make_import_file(conn, sha256="b" * 64)
    got = await import_files.get_by_sha(conn, "example", "b" * 64)
    assert got["id"] == row["id"]
    assert await import_files.get_by_sha(conn, "example", "c" * 64) is None


async def test_list_files_paging_and_filters(conn: AsyncConnection) -> None:
    for i in range(5):
        await make_import_file(conn, received_at=NOW - timedelta(minutes=i))
    await make_import_file(conn, site_id="other")
    await make_import_file(conn, status="failed", received_at=NOW - timedelta(days=1))
    page = await import_files.list_files(conn, "example", limit=3, offset=0)
    assert len(page) == 3
    assert page[0]["received_at"] >= page[1]["received_at"]
    rest = await import_files.list_files(conn, "example", limit=3, offset=3)
    assert len(rest) == 3
    failed = await import_files.list_files(conn, "example", status="failed")
    assert [f["status"] for f in failed] == ["failed"]
    assert await import_files.count_files(conn, "example") == 6
    assert await import_files.count_files(conn, "example", status="failed") == 1


async def test_waiting_counts(conn: AsyncConnection) -> None:
    assert await import_files.files_waiting(conn) == 0
    assert not await import_files.live_work_waiting(conn)
    await make_import_file(conn, priority="backfill")
    await make_import_file(conn, site_id="other", status="success")
    assert await import_files.files_waiting(conn) == 1
    assert await import_files.files_waiting(conn, "example") == 1
    assert not await import_files.live_work_waiting(conn)
    await make_import_file(conn, site_id="other")
    assert await import_files.live_work_waiting(conn)
    assert await import_files.live_work_waiting(conn, "other")
    assert not await import_files.live_work_waiting(conn, "example")
    assert await import_files.sites_with_new_files(conn) == ["example", "other"]


async def test_expired_success_files_and_mark_deleted(conn: AsyncConnection) -> None:
    old = await make_import_file(conn, status="success", finished_at=NOW - timedelta(days=8))
    await make_import_file(conn, status="success", finished_at=NOW - timedelta(days=1))
    await make_import_file(conn, status="failed", finished_at=NOW - timedelta(days=30))
    await make_import_file(
        conn, status="success", finished_at=NOW - timedelta(days=30), object_deleted_at=NOW
    )
    expired = await import_files.expired_success_files(conn, 7, now=NOW)
    assert [f["id"] for f in expired] == [old["id"]]
    await import_files.mark_deleted(conn, old["id"])
    assert await import_files.expired_success_files(conn, 7, now=NOW) == []
    assert (await import_files.get_file(conn, old["id"]))["object_deleted_at"] is not None


async def test_last_received_by_source(conn: AsyncConnection) -> None:
    await make_import_file(conn, source="cdn", received_at=NOW - timedelta(hours=2))
    await make_import_file(
        conn,
        source="cdn",
        received_at=NOW - timedelta(minutes=5),
        max_ts=NOW - timedelta(minutes=7),
    )
    await make_import_file(conn, source="origin", received_at=NOW - timedelta(hours=3))
    await make_import_file(conn, source="origin", priority="backfill", received_at=NOW)
    got = await import_files.last_received_by_source(conn, "example")
    assert got["cdn"]["last_file_at"] == NOW - timedelta(minutes=5)
    assert got["cdn"]["last_event_at"] == NOW - timedelta(minutes=7)
    assert got["origin"]["last_file_at"] == NOW - timedelta(hours=3)
    all_files = await import_files.last_received_by_source(conn, "example", live_only=False)
    assert all_files["origin"]["last_file_at"] == NOW
    assert await import_files.last_received_by_source(conn, "nobody") == {}


async def test_overlapping_files(conn: AsyncConnection) -> None:
    base = await make_import_file(
        conn, status="success", min_ts=NOW - timedelta(hours=1), max_ts=NOW
    )
    overlap = await make_import_file(
        conn, status="success", min_ts=NOW - timedelta(minutes=30), max_ts=NOW + timedelta(hours=1)
    )
    await make_import_file(
        conn, status="success", min_ts=NOW + timedelta(hours=2), max_ts=NOW + timedelta(hours=3)
    )
    await make_import_file(
        conn, status="success", source="cdn", min_ts=NOW - timedelta(hours=1), max_ts=NOW
    )
    await make_import_file(
        conn, status="success", site_id="other", min_ts=NOW - timedelta(hours=1), max_ts=NOW
    )
    got = await import_files.overlapping_files(conn, "example", base["id"])
    assert [f["id"] for f in got] == [overlap["id"]]


async def test_overlapping_files_without_range(conn: AsyncConnection) -> None:
    row = await make_import_file(conn, status="success")
    assert await import_files.overlapping_files(conn, "example", row["id"]) == []
