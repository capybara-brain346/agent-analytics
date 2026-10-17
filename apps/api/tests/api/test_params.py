async def test_site_default_and_unknown(client, rng):
    assert (await client.get("/api/runs")).status_code == 200
    r = await client.get("/api/runs", params={"site": "nope"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "site_not_found"


async def test_bad_params_422(client):
    for params in (
        {"class": "7"},
        {"class": "x"},
        {"from": "2026-10-17T12:00:00Z", "to": "2026-10-17T11:00:00Z"},
        {"from": "garbage"},
    ):
        r = await client.get("/api/overview", params=params)
        assert r.status_code == 422, params


async def test_class_comma_list_and_default_range(client, monkeypatch):
    from datetime import UTC, datetime

    from src.routes import params

    monkeypatch.setattr(params, "utcnow", lambda: datetime(2026, 10, 17, 12, tzinfo=UTC))
    r = await client.get("/api/overview", params={"class": "1,2"})
    body = r.json()
    assert r.status_code == 200
    assert body["window"]["classes"] == [1, 2]
    assert body["window"]["start"].startswith("2026-10-16T12:00")
    assert body["window"]["end"].startswith("2026-10-17T12:00")


async def test_pagination_bad_limit(client):
    assert (await client.get("/api/events", params={"limit": 0})).status_code == 422
    assert (await client.get("/api/events", params={"limit": 500})).status_code == 422
