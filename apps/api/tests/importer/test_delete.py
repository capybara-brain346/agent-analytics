import pytest

from src.models.domain import Lane
from src.services import pairing
from src.services.importer import DeleteBlocked, delete_import, import_due_files
from src.store import import_files, locks
from tests.factories import NOW
from tests.fakes import MemoryInbox
from tests.importer.test_importer import add_file, cdn_record, origin_line, rows


async def paired_files(conn, inbox):
    cdn = await add_file(conn, inbox, [cdn_record(0, rid="e1", status=200)], source="cdn")
    origin = await add_file(conn, inbox, [origin_line(0, rid="e1", status=500)], source="origin")
    await import_due_files(conn, "example", inbox, now=NOW)
    assert (await pairing.pair_events(conn, "example", now=NOW))["paired"] == 1
    return cdn, origin


async def test_delete_origin_file_keeps_cdn_half(pool, conn, config_dir):
    inbox = MemoryInbox()
    cdn, origin = await paired_files(conn, inbox)

    result = await delete_import(str(origin["id"]), inbox)
    assert result.files_reimported == [str(cdn["id"])]
    assert await import_files.get_file(conn, origin["id"]) is None
    assert origin["object_key"] not in inbox.objects

    await import_due_files(conn, "example", inbox, now=NOW)
    [row] = await rows(conn)
    assert (row["source"], row["origin_status"], row["edge_status"]) == ("cdn", None, 200)


async def test_delete_is_refused_when_a_partner_cannot_be_read(pool, conn, config_dir):
    inbox = MemoryInbox()
    cdn, origin = await paired_files(conn, inbox)
    await import_files.mark_deleted(conn, cdn["id"])

    with pytest.raises(DeleteBlocked):
        await delete_import(str(origin["id"]), inbox)
    [row] = await rows(conn)
    assert row["source"] == "paired"
    assert (await import_files.get_file(conn, origin["id"]))["status"] == "success"


async def test_delete_waits_for_a_pipeline_run(pool, conn, config_dir):
    inbox = MemoryInbox()
    f = await add_file(conn, inbox, [origin_line(0)])
    async with locks.site_lane_lock(conn, "example", Lane.FAST) as got:
        assert got
        with pytest.raises(DeleteBlocked):
            await delete_import(str(f["id"]), inbox)
    assert await import_files.get_file(conn, f["id"]) is not None
