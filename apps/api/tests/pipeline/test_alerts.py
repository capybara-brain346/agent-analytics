from datetime import timedelta

from src.services import alerts
from src.store import alerts as alerts_store
from tests.factories import make_import_file


async def test_no_data_alert_names_source_and_resolves(conn, config_dir, now):
    await make_import_file(conn, source="cdn", received_at=now - timedelta(minutes=5))
    await make_import_file(conn, source="origin", received_at=now - timedelta(minutes=90))
    await alerts.check_no_data(conn, now)
    rows = await alerts_store.list_alerts(conn, open_only=True)
    assert [(r["site_id"], r["kind"], r["source"]) for r in rows] == [
        ("example", "no_data", "origin")
    ]
    assert "origin" in rows[0]["message"]
    await alerts.check_no_data(conn, now)
    assert len(await alerts_store.list_alerts(conn, open_only=True)) == 1
    await make_import_file(conn, source="origin", received_at=now - timedelta(minutes=1))
    await alerts.check_no_data(conn, now)
    assert await alerts_store.list_alerts(conn, open_only=True) == []
    assert len(await alerts_store.list_alerts(conn)) == 1


async def test_backfill_files_do_not_count_as_live_data(conn, config_dir, now):
    await make_import_file(conn, source="cdn", received_at=now - timedelta(minutes=90))
    await make_import_file(
        conn, source="cdn", priority="backfill", received_at=now - timedelta(minutes=1)
    )
    await alerts.check_no_data(conn, now)
    assert len(await alerts_store.list_alerts(conn, open_only=True)) == 1


async def test_source_that_never_sent_does_not_alert(conn, config_dir, now):
    await alerts.check_no_data(conn, now)
    assert await alerts_store.list_alerts(conn) == []
