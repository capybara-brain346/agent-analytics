from src.config import get_settings
from tests.factories import make_import_file
from tests.ingest.conftest import AUTH


async def test_byte_quota_counts_files_of_every_process(api, conn, monkeypatch):
    # The files were stored by another API replica: this process has no memory of them.
    monkeypatch.setenv("INGEST_BYTES_PER_DAY", "1000")
    get_settings.cache_clear()
    await make_import_file(conn, site_id="solo", size_bytes=990, received_at=_now())
    r = await api.post("/ingest", params={"site": "solo"}, content=b"x" * 50, headers=AUTH)
    assert r.status_code == 429
    assert r.headers["retry-after"]


async def test_old_files_do_not_count(api, conn, monkeypatch):
    from datetime import timedelta

    monkeypatch.setenv("INGEST_BYTES_PER_DAY", "1000")
    get_settings.cache_clear()
    await make_import_file(
        conn, site_id="solo", size_bytes=990, received_at=_now() - timedelta(days=2)
    )
    r = await api.post("/ingest", params={"site": "solo"}, content=b"x" * 50, headers=AUTH)
    assert r.status_code == 202


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


async def test_uploads_and_cli_files_do_not_count(api, conn, monkeypatch):
    monkeypatch.setenv("INGEST_BYTES_PER_DAY", "1000")
    get_settings.cache_clear()
    for entry in ("upload", "cli", "bucket"):
        await make_import_file(
            conn, site_id="solo", size_bytes=990, received_at=_now(), entry=entry
        )
    r = await api.post("/ingest", params={"site": "solo"}, content=b"x" * 50, headers=AUTH)
    assert r.status_code == 202
