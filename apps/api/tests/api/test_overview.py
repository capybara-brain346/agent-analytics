from datetime import timedelta

from tests.factories import NOW, make_alert, make_pipeline_run, make_recommendation


async def test_overview_empty(client, rng):
    r = await client.get("/api/overview", params=rng)
    assert r.status_code == 200
    body = r.json()
    assert body["empty"] is True
    assert body["key_numbers"]["total_requests"]["value"] == 0
    assert body["top_pages"] == []
    assert len(body["traffic_by_class"]) == 6
    assert body["coverage"]["sources_configured"] == ["cdn", "origin"]


async def test_overview_numbers(client, rng, traffic):
    await traffic()
    body = (await client.get("/api/overview", params=rng)).json()
    k = body["key_numbers"]
    assert body["empty"] is False
    assert k["total_requests"] == {
        "value": 5,
        "previous": 0,
        "change_pct": None,
        "unit": "requests",
        "label": "observed",
    }
    assert k["ai_or_automated_share"]["value"] == 60.0
    assert k["distinct_agents"]["value"] == 1
    assert k["error_rate"]["value"] == 40.0
    assert k["denial_rate"]["value"] == 20.0
    by_class = {c["traffic_class"]: c for c in body["traffic_by_class"]}
    assert by_class[2]["requests"] == 3 and by_class[2]["high"] == 3
    assert by_class[5]["medium"] == 1
    assert by_class[2]["share_pct"] == 60.0
    assert body["unclassified_requests"] == 1
    assert body["top_agents"] == [{"agent": "gptbot", "traffic_class": 2, "requests": 3}]
    assert body["top_pages"][0] == {
        "path": "/pricing",
        "agent_requests": 2,
        "errors": 1,
        "blocks": 1,
    }
    assert sum(p["total"] for p in body["trend"]) == 5
    assert set(body["coverage"]["sources_present"]) == {"cdn", "origin"}
    assert body["coverage"]["unknown_share_pct"] == 0.0


async def test_overview_class_filter_and_previous_period(client, rng, traffic, conn):
    await traffic()
    r = await client.get("/api/overview", params=rng | {"class": 5})
    assert r.json()["key_numbers"]["total_requests"]["value"] == 1
    assert [c["traffic_class"] for c in r.json()["traffic_by_class"]] == [5]
    # previous period = same span before "from"
    body = (
        await client.get(
            "/api/overview",
            params={
                "from": (NOW - timedelta(minutes=2, seconds=30)).isoformat(),
                "to": (NOW + timedelta(hours=1)).isoformat(),
            },
        )
    ).json()
    assert body["key_numbers"]["total_requests"]["value"] == 2
    assert body["key_numbers"]["total_requests"]["previous"] == 3


async def test_overview_freshness_and_alerts(client, rng, conn):
    await make_pipeline_run(
        conn, started_at=NOW - timedelta(minutes=20), finished_at=NOW - timedelta(minutes=10)
    )
    body = (await client.get("/api/overview", params=rng)).json()
    assert body["freshness"]["state"] == "ok"
    assert body["freshness"]["text"] == "Data up to 11:50"
    await make_pipeline_run(
        conn, status="failed", failed_step="verify", started_at=NOW, finished_at=NOW
    )
    body = (await client.get("/api/overview", params=rng)).json()
    assert body["freshness"]["state"] == "last_run_failed"
    assert body["freshness"]["failed_step"] == "verify"
    assert body["freshness"]["data_up_to"].startswith("2026-10-17T11:50")
    await make_alert(conn)
    body = (await client.get("/api/overview", params=rng)).json()
    assert body["open_alerts_count"] == 1
    assert body["freshness"]["state"] == "alert_no_data"


async def test_overview_top_recommendations(client, rng, conn):
    from tests.factories import make_recommendation_run

    run = await make_recommendation_run(conn)
    for i in range(1, 5):
        await make_recommendation(conn, run_id=run["id"], stable_id=f"s{i}", rank=i, score=10 - i)
    await make_recommendation(conn, run_id=run["id"], stable_id="g", rank=9, change="gone")
    body = (await client.get("/api/overview", params=rng)).json()
    assert [r["rank"] for r in body["top_recommendations"]] == [1, 2, 3]
