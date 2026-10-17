from datetime import timedelta

from src.config import get_settings
from tests.factories import NOW, make_import_file

LINE = b"some old log line\n"


async def test_upload_is_backfill_upload_entry(api, inbox, conn):
    r = await api.post("/api/imports/upload", params={"site": "solo"}, content=LINE)
    assert r.status_code == 202
    cur = await conn.execute(
        "select priority, entry, status from import_files where id = %s", [r.json()["file_id"]]
    )
    assert await cur.fetchone() == ("backfill", "upload", "new")
    assert len(inbox.objects) == 1


async def test_upload_duplicate_and_errors(api, inbox):
    assert (
        await api.post("/api/imports/upload", params={"site": "solo"}, content=LINE)
    ).status_code == 202
    dup = await api.post("/api/imports/upload", params={"site": "solo"}, content=LINE)
    assert dup.status_code == 200 and dup.json()["duplicate"] is True
    assert (
        await api.post("/api/imports/upload", params={"site": "ghost"}, content=LINE)
    ).status_code == 404
    assert (
        await api.post("/api/imports/upload", params={"site": "example"}, content=LINE)
    ).status_code == 422
    assert len(inbox.objects) == 1


async def test_upload_limit_is_upload_max(api, inbox, monkeypatch):
    monkeypatch.setenv("UPLOAD_MAX_BYTES", "5")
    get_settings.cache_clear()
    r = await api.post("/api/imports/upload", params={"site": "solo"}, content=LINE)
    assert r.status_code == 413 and inbox.objects == {}


async def test_upload_has_no_ingest_rate_limit(api, monkeypatch):
    monkeypatch.setenv("INGEST_RATE_PER_MINUTE", "1")
    get_settings.cache_clear()
    for i in range(3):
        r = await api.post(
            "/api/imports/upload", params={"site": "solo"}, content=LINE + bytes([65 + i])
        )
        assert r.status_code == 202


async def test_list_with_counts_paging_and_overlap(api, conn):
    base = dict(site_id="example", source="cdn", status="success", finished_at=NOW)
    a = await make_import_file(
        conn,
        **base,
        min_ts=NOW - timedelta(hours=2),
        max_ts=NOW - timedelta(hours=1),
        lines_rejected=3,
    )
    b = await make_import_file(conn, **base, min_ts=NOW - timedelta(minutes=90), max_ts=NOW)
    await make_import_file(conn, site_id="solo", source="origin")
    r = await api.get("/api/imports", params={"site": "example"})
    body = r.json()
    assert body["total"] == 2 and len(body["items"]) == 2
    by_id = {i["id"]: i for i in body["items"]}
    assert by_id[str(a["id"])]["rejects_count"] == 3
    assert "overlaps" in by_id[str(a["id"])]["overlap_warning"]["message"]
    assert by_id[str(b["id"])]["delete_on"] is not None
    page = (
        await api.get("/api/imports", params={"site": "example", "limit": 1, "offset": 1})
    ).json()
    assert len(page["items"]) == 1 and page["total"] == 2
    assert (await api.get("/api/imports", params={"site": "ghost"})).status_code == 404
    assert (await api.get("/api/imports", params={"limit": 0})).status_code == 422
    assert (await api.get("/api/imports")).json()["total"] == 3
