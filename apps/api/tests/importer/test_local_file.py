import gzip

import pytest

from src.services.importer import import_local_file
from src.store import events, import_files
from tests.fakes import MemoryInbox
from tests.importer.test_importer import origin_line


@pytest.fixture
def log_file(tmp_path):
    path = tmp_path / "access.log.gz"
    path.write_bytes(gzip.compress("\n".join([origin_line(0), origin_line(1)]).encode()))
    return path


async def test_import_later(pool, conn, log_file, config_dir, settings):
    inbox = MemoryInbox()
    res = await import_local_file(
        log_file, "example", now=False, force=False, source="origin", inbox=inbox
    )
    f = await import_files.get_file(conn, res["file_id"])
    assert (f["status"], f["priority"], f["entry"], f["source"]) == (
        "new",
        "backfill",
        "cli",
        "origin",
    )
    assert len(inbox.objects) == 1


async def test_import_now_and_duplicate_and_force(pool, conn, log_file, config_dir, settings):
    inbox = MemoryInbox()
    kw = {"source": "origin", "inbox": inbox}
    res = await import_local_file(log_file, "example", now=True, force=False, **kw)
    assert res["counts"]["lines_imported"] == 2
    assert await events.count_events(conn, "example") == 2

    dup = await import_local_file(log_file, "example", now=True, force=False, **kw)
    assert dup["duplicate"] is True and dup["file_id"] == res["file_id"]
    assert dup["counts"]["files"] == 0
    assert len(inbox.objects) == 1

    again = await import_local_file(log_file, "example", now=True, force=True, **kw)
    assert again["reimport"] is True
    assert again["counts"]["lines_imported"] == 2
    assert await events.count_events(conn, "example") == 2


async def test_source_required_for_two_source_site(pool, log_file, config_dir, settings):
    with pytest.raises(ValueError):
        await import_local_file(log_file, "example", now=False, force=False, inbox=MemoryInbox())


async def test_source_defaults_for_single_source_site(pool, conn, log_file, config_dir, settings):
    (config_dir / "sites" / "solo.yaml").write_text("site_id: solo\nsources: [origin]\n")
    res = await import_local_file(log_file, "solo", now=False, force=False, inbox=MemoryInbox())
    assert (await import_files.get_file(conn, res["file_id"]))["source"] == "origin"


async def test_default_inbox_and_source_none(
    pool, conn, log_file, config_dir, settings, monkeypatch
):
    from src.services.importer import service

    inbox = MemoryInbox()
    monkeypatch.setattr(service, "get_inbox", lambda: inbox)
    (config_dir / "sites" / "solo.yaml").write_text("site_id: solo\nsources: [origin]\n")
    res = await import_local_file(log_file, "solo", now=True, force=False, source=None)
    assert res["counts"]["lines_imported"] == 2
