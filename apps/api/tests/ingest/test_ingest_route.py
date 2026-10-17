import gzip

from src.config import get_settings
from src.services import ingest
from tests.ingest.conftest import AUTH

LINE = b'1.2.3.4 - - [17/Oct/2026:12:00:00 +0000] "GET /pricing HTTP/1.1" 200 5\n'


async def post(api, params, body=LINE, headers=AUTH):
    return await api.post("/ingest", params=params, content=body, headers=headers)


async def test_accepts_chunk_and_queues_file(api, inbox, conn):
    r = await post(api, {"site": "solo"})
    assert r.status_code == 202
    body = r.json()
    assert body["duplicate"] is False
    (key,) = inbox.objects
    assert key.startswith("solo/origin/") and key.endswith(".log")
    cur = await conn.execute(
        "select status, priority, entry, source, size_bytes from import_files where id = %s",
        [body["file_id"]],
    )
    assert await cur.fetchone() == ("new", "live", "ingest", "origin", len(LINE))


async def test_gzip_body_stored_as_is(api, inbox):
    data = gzip.compress(LINE)
    r = await post(api, {"site": "solo"}, data, {**AUTH, "Content-Encoding": "gzip"})
    assert r.status_code == 202
    (key,) = inbox.objects
    assert key.endswith(".gz")
    assert inbox.objects[key] == data


async def test_duplicate_returns_200_and_deletes_object(api, inbox):
    first = (await post(api, {"site": "solo"})).json()
    second = await post(api, {"site": "solo"})
    assert second.status_code == 200
    assert second.json() == {"file_id": first["file_id"], "duplicate": True}
    assert len(inbox.objects) == 1


async def test_bad_or_missing_token_401(api, inbox):
    assert (await post(api, {"site": "solo"}, headers={})).status_code == 401
    bad = {"Authorization": "Bearer nope"}
    assert (await post(api, {"site": "solo"}, headers=bad)).status_code == 401
    assert inbox.objects == {}


async def test_unknown_site_gives_same_401_as_bad_token(api):
    ghost = await post(api, {"site": "ghost"})
    bad = await post(api, {"site": "solo"}, headers={"Authorization": "Bearer nope"})
    assert ghost.status_code == bad.status_code == 401
    assert ghost.json() == bad.json()
    assert (await post(api, {"site": "ghost"}, headers={})).status_code == 401


async def test_source_rules(api, inbox):
    assert (await post(api, {"site": "example"})).status_code == 422
    assert (await post(api, {"site": "solo", "source": "cdn"})).status_code == 422
    ok = await post(api, {"site": "example", "source": "cdn"})
    assert ok.status_code == 202
    assert next(iter(inbox.objects)).startswith("example/cdn/")


async def test_too_large_by_stream_413(api, inbox, monkeypatch):
    monkeypatch.setenv("INGEST_MAX_BYTES", "10")
    get_settings.cache_clear()

    async def body():
        yield b"x" * 6
        yield b"x" * 6

    r = await api.post("/ingest", params={"site": "solo"}, content=body(), headers=AUTH)
    assert r.status_code == 413
    assert inbox.objects == {}


async def test_too_large_by_content_length_413(api, inbox, monkeypatch):
    monkeypatch.setenv("INGEST_MAX_BYTES", "10")
    get_settings.cache_clear()
    assert (await post(api, {"site": "solo"}, b"x" * 11)).status_code == 413
    assert inbox.objects == {}


async def test_empty_body_400(api):
    assert (await post(api, {"site": "solo"}, b"")).status_code == 400


async def test_rate_limit_429(api, monkeypatch):
    monkeypatch.setenv("INGEST_RATE_PER_MINUTE", "2")
    get_settings.cache_clear()
    codes = [
        (await post(api, {"site": "solo"}, LINE + bytes([65 + i]))).status_code for i in range(3)
    ]
    assert codes == [202, 202, 429]


async def test_byte_quota_429(api, monkeypatch):
    monkeypatch.setenv("INGEST_BYTES_PER_DAY", str((len(LINE) + 1) * 2))
    get_settings.cache_clear()
    codes = [
        (await post(api, {"site": "solo"}, LINE + bytes([65 + i]))).status_code for i in range(3)
    ]
    assert codes == [202, 202, 429]


async def test_token_check_helper(config_dir):
    assert await ingest.check_site_token("example", "dev-token") is True
    assert await ingest.check_site_token("example", "other") is False
