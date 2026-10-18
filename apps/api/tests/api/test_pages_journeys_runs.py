from datetime import UTC, timedelta

from tests.factories import (
    NOW,
    make_journey_step,
    make_page_stats,
    make_pipeline_run,
    make_recommendation,
    make_session,
)


async def test_pages_empty_lists_key_pages_with_zero(client, rng):
    body = (await client.get("/api/pages", params=rng)).json()
    paths = {i["path"]: i for i in body["items"]}
    assert set(paths) == {"/pricing", "/products", "/docs/api", "/signup", "/checkout"}
    assert paths["/pricing"]["requests"] == 0 and paths["/pricing"]["error_rate_pct"] is None
    assert "key" in paths["/pricing"]["tags"] and "conversion" in paths["/signup"]["tags"]


async def test_pages_sum_hours_views_and_sessions(client, rng, conn):
    h = NOW.replace(minute=0)
    await make_page_stats(conn, hour=h, requests=10, n_2xx=8, n_4xx=2, n_403=2, retries=1)
    await make_page_stats(conn, hour=h - timedelta(hours=1), requests=10, n_2xx=10)
    await make_page_stats(conn, hour=h, traffic_class=5, requests=4, n_2xx=4)
    await make_page_stats(conn, hour=h, path="/other", tags=[], requests=1, n_5xx=1, n_2xx=0)
    await make_session(conn, session_id="a", pages_in_order=["/pricing", "/other"])
    await make_session(conn, session_id="b", claimed_agent="claudebot", pages_in_order=["/pricing"])
    body = (await client.get("/api/pages", params=rng)).json()
    pricing = next(i for i in body["items"] if i["path"] == "/pricing")
    assert pricing["requests"] == 24 and pricing["agent_requests"] == 20
    assert pricing["error_rate_pct"] == round(100 * 2 / 24, 2)
    assert pricing["block_rate_pct"] == round(100 * 2 / 24, 2)
    assert pricing["retries"] == 1 and pricing["sessions"] == 2 and pricing["distinct_agents"] == 2
    assert body["items"][0]["path"] == "/pricing"  # agent-heavy first

    async def paths(**p):
        r = await client.get("/api/pages", params=rng | p)
        assert r.status_code == 200, r.text
        return [i["path"] for i in r.json()["items"]]

    assert await paths(view="errors") == ["/pricing", "/other"]
    assert await paths(view="blocks") == ["/pricing"]
    assert await paths(view="retries") == ["/pricing"]
    assert await paths(view="agent_heavy") == ["/pricing", "/other"]
    never = await paths(view="never_reached")
    assert set(never) == {"/products", "/docs/api"}
    assert (await paths(**{"class": "5"}))[0] == "/pricing"
    assert (await client.get("/api/pages", params=rng | {"view": "x"})).status_code == 422


async def test_page_detail(client, rng, conn):
    h = NOW.replace(minute=0)
    await make_page_stats(conn, hour=h, requests=10, n_2xx=0, n_403=10, n_4xx=10)
    await make_page_stats(conn, hour=h, traffic_class=5, requests=4, n_2xx=4)
    await make_session(conn, session_id="a", pages_in_order=["/pricing"])
    await make_recommendation(conn, target="/pricing")
    body = (await client.get("/api/pages", params=rng | {"path": "/pricing"})).json()
    assert body["page"]["path"] == "/pricing"
    assert body["in_sitemap"] is True and body["access_policy"] == "allowed"
    by_class = {c["traffic_class"]: c for c in body["by_class"]}
    assert by_class[2]["n_403"] == 10 and by_class[5]["n_2xx"] == 4
    assert body["over_time"][0]["requests"] == 14
    assert body["agents"] == [{"claimed_agent": "gptbot", "traffic_class": 2, "sessions": 1}]
    assert body["sessions"][0]["session_id"] == "a"
    assert body["recommendations"][0]["target"] == "/pricing"
    blocked = await client.get("/api/pages", params=rng | {"path": "/admin"})
    assert blocked.status_code == 404
    key = (await client.get("/api/pages", params=rng | {"path": "/products"})).json()
    assert key["page"]["requests"] == 0


async def test_journeys(client, rng, conn):
    h = NOW.replace(minute=0)
    for i in range(3):
        await make_session(conn, session_id=f"a{i}", journeys_reached={"signup": 1})
    await make_session(conn, session_id="b", journeys_reached={"signup": 2})
    await make_session(conn, session_id="c", open=True, journeys_reached={"signup": 3})
    await make_session(conn, session_id="d", traffic_class=4, journeys_reached={"signup": 2})
    # Retry/loop counts are distinct sessions (retry_paths), not the sum of hourly rows.
    for i in range(3):
        await make_session(
            conn,
            session_id=f"r{i}",
            pages_in_order=["/pricing", "/signup"],
            has_retry=True,
            retry_paths=["/signup"],
            journeys_reached={"signup": 2},
        )
    for hour in (h, h - timedelta(hours=1)):  # hourly rows must not be added up
        await make_journey_step(conn, hour=hour, step_no=2, step_path="/signup")
    body = (await client.get("/api/journeys", params=rng)).json()
    assert [j["journey_id"] for j in body] == ["signup", "docs"]
    signup = body[0]
    assert signup["critical"] is True
    assert signup["steps"] == ["/pricing", "/signup", "/signup/confirm"]
    assert signup["outcome"]["label"] == "unknown"
    c2 = next(c for c in signup["by_class"] if c["traffic_class"] == 2)
    assert c2["sessions"] == 8 and c2["reached"] == [8, 5, 1] and c2["stopped_at"] == [3, 4, 1]
    assert c2["retry_or_loop"] == [0, 3, 0]
    c4 = next(c for c in signup["by_class"] if c["traffic_class"] == 4)
    assert c4["reached"] == [1, 1, 0]
    assert body[1]["by_class"] == []
    one = (await client.get("/api/journeys/signup", params=rng | {"class": "4"})).json()
    assert [c["traffic_class"] for c in one["by_class"]] == [4]


async def test_journey_404(client, rng):
    assert (await client.get("/api/journeys/zzz", params=rng)).status_code == 404


async def test_runs(client, conn):
    ok = await make_pipeline_run(
        conn,
        started_at=NOW - timedelta(minutes=10),
        finished_at=NOW - timedelta(minutes=9, seconds=48),
        counts={"import": {"files": 2}},
    )
    bad = await make_pipeline_run(
        conn,
        status="failed",
        failed_step="verify",
        error="dns",
        started_at=NOW - timedelta(minutes=5),
    )
    slow = await make_pipeline_run(conn, lane="slow", started_at=NOW)
    body = (await client.get("/api/runs")).json()
    assert [r["id"] for r in body["items"]] == [str(slow["id"]), str(bad["id"]), str(ok["id"])]
    assert body["page"]["total"] == 3
    assert next(r for r in body["items"] if r["id"] == str(ok["id"]))["duration_seconds"] == 12.0
    only = (await client.get("/api/runs", params={"lane": "fast"})).json()
    assert only["page"]["total"] == 2
    failed = (await client.get("/api/runs", params={"status": "failed"})).json()
    assert failed["items"][0]["failed_step"] == "verify" and failed["items"][0]["error"] == "dns"
    assert (await client.get("/api/runs", params={"lane": "x"})).status_code == 422
    one = (await client.get(f"/api/runs/{ok['id']}")).json()
    assert one["counts"] == {"import": {"files": 2}}
    assert (await client.get("/api/runs/00000000-0000-0000-0000-000000000000")).status_code == 404
    assert (await client.get("/api/runs/abc")).status_code == 422


async def test_runs_empty(client):
    body = (await client.get("/api/runs")).json()
    assert body["items"] == [] and body["page"]["total"] == 0


async def test_hour_bounds_do_not_depend_on_db_time_zone(conn):
    # A zone with a half-hour offset would cut the hour at :30 UTC and drop the first hour.
    from src.store import queries
    from tests.factories import make_event, make_verdict

    h = NOW.replace(minute=0)
    await make_page_stats(conn, hour=h, requests=7)
    v = await make_verdict(conn, classified=True)
    await make_event(conn, ts=h + timedelta(minutes=40), verdict_id=v["id"])
    await conn.execute("set time zone 'Asia/Kolkata'")
    f = queries.Filters("example", start=h + timedelta(minutes=40), end=h + timedelta(hours=2))
    items = await queries.list_pages(conn, f)
    assert {i["path"]: i["requests"] for i in items}["/pricing"] == 7
    buckets = [r["bucket"] for r in await queries.trend(conn, f)]
    assert buckets and all(b.astimezone(UTC).minute == 0 for b in buckets)
    assert await queries.list_agents(conn, f) is not None
