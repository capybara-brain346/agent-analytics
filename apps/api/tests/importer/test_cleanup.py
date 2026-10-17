from datetime import timedelta

from src.services import cleanup
from src.store import import_files
from tests.factories import NOW, make_event, make_import_file
from tests.fakes import MemoryInbox


async def file_at(conn, inbox, name, age_days, status="success"):
    key = f"inbox/example/{name}"
    inbox.put_text(key, "x")
    return await make_import_file(
        conn, object_key=key, status=status, finished_at=NOW - timedelta(days=age_days)
    )


async def test_deletes_only_old_success_files(conn):
    inbox = MemoryInbox()
    old = await file_at(conn, inbox, "old", 8)
    new = await file_at(conn, inbox, "new", 2)
    failed = await file_at(conn, inbox, "failed", 30, status="failed")
    n = await cleanup.delete_expired_raw_files(conn, inbox, retention_days=7, now=NOW)
    assert n == 1
    assert set(inbox.objects) == {new["object_key"], failed["object_key"]}
    got = await import_files.get_file(conn, old["id"])
    assert got["object_deleted_at"] is not None and got["status"] == "success"
    assert (await import_files.get_file(conn, failed["id"]))["object_deleted_at"] is None
    assert await cleanup.delete_expired_raw_files(conn, inbox, retention_days=7, now=NOW) == 0


async def test_delete_error_keeps_file_for_next_run(conn):
    class Broken(MemoryInbox):
        async def delete(self, key):
            raise OSError("down")

    inbox = Broken()
    f = await file_at(conn, inbox, "old", 9)
    assert await cleanup.delete_expired_raw_files(conn, inbox, retention_days=7, now=NOW) == 0
    assert (await import_files.get_file(conn, f["id"]))["object_deleted_at"] is None


async def test_drop_old_partitions(conn):
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    await make_event(conn, ts=now - timedelta(days=60))
    await make_event(conn, ts=now)
    assert await cleanup.drop_expired_partitions(keep_days=30) >= 1
    cur = await conn.execute("select count(*) from events")
    assert (await cur.fetchone())[0] == 1


async def test_run_cleanup_reports_both(conn, settings):
    result = await cleanup.run_cleanup(conn, MemoryInbox(), now=NOW)
    assert set(result) == {"files_deleted", "partitions_dropped"}


async def test_no_args_uses_pool_and_default_inbox(pool, conn, monkeypatch):
    from src.services.cleanup import service

    inbox = MemoryInbox()
    old = await file_at(conn, inbox, "old", 400)
    monkeypatch.setattr(service, "get_inbox", lambda: inbox)
    assert await cleanup.delete_expired_raw_files() == 1
    assert inbox.objects == {}
    assert (await import_files.get_file(conn, old["id"]))["object_deleted_at"] is not None
