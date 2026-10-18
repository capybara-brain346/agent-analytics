import pytest

from src.config import get_settings

TOKEN = "dashboard-secret"


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setenv("API_TOKEN", TOKEN)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


PROTECTED = [
    ("get", "/api/runs?site=example"),
    ("post", "/api/recommendations/generate?site=example"),
    ("post", "/api/imports/upload?site=solo"),
]


@pytest.mark.parametrize(("method", "url"), PROTECTED)
async def test_api_requires_token_when_set(client, secured, config_dir, method, url):
    r = await getattr(client, method)(url)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    r = await getattr(client, method)(url, headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


async def test_api_accepts_right_token(client, secured, config_dir):
    r = await client.get("/api/runs?site=example", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200


async def test_health_and_ingest_do_not_use_the_api_token(client, secured, config_dir):
    assert (await client.get("/livez")).status_code == 200
    assert (await client.get("/health")).status_code in (200, 503)
    r = await client.post("/ingest?site=example", content=b"x")
    assert r.status_code == 401
    assert r.json()["detail"] == "Bad token"  # the site token check, not the API token


async def test_api_open_when_token_unset(client, config_dir):
    assert (await client.get("/api/runs?site=example")).status_code == 200
