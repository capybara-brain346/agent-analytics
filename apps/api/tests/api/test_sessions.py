from datetime import timedelta

from tests.factories import NOW, make_event, make_recommendation, make_session, make_session_event


async def test_sessions_empty(client, rng):
    body = (await client.get("/api/sessions", params=rng)).json()
    assert body["items"] == [] and body["page"]["total"] == 0


async def test_sessions_union_and_filters(client, rng, conn):
    await make_session(conn, session_id="closed", has_retry=True, reached_conversion=True)
    await make_session(
        conn,
        session_id="open",
        open=True,
        traffic_class=4,
        confidence="low",
        claimed_agent=None,
        has_loop=True,
        journeys_reached={"signup": 2},
    )
    await make_session(
        conn, session_id="old", started=NOW - timedelta(days=3), last_seen=NOW - timedelta(days=3)
    )
    body = (await client.get("/api/sessions", params=rng)).json()
    got = {s["session_id"]: s for s in body["items"]}
    assert set(got) == {"closed", "open"}
    assert got["open"]["state"] == "in_progress" and got["open"]["in_progress"] is True
    assert got["open"]["last_event_age_seconds"] >= 0
    assert got["closed"]["state"] == "closed" and got["closed"]["last_event_age_seconds"] is None
    assert got["open"]["class_name"] == "Browser automation / agent-like"

    async def ids(**p):
        r = await client.get("/api/sessions", params=rng | p)
        assert r.status_code == 200, r.text
        return {s["session_id"] for s in r.json()["items"]}

    assert await ids(**{"class": "4"}) == {"open"}
    assert await ids(state="in_progress") == {"open"}
    assert await ids(state="closed") == {"closed"}
    assert await ids(has_retry="true") == {"closed"}
    assert await ids(has_loop="true") == {"open"}
    assert await ids(reached_conversion="true") == {"closed"}
    assert await ids(confidence="low") == {"open"}
    assert await ids(agent="gptbot") == {"closed"}
    assert await ids(journey="signup") == {"open"}
    assert await ids(journey="signup", reached_step=2) == {"open"}
    assert await ids(journey="signup", reached_step=3) == set()
    assert (await client.get("/api/sessions", params=rng | {"journey": "zzz"})).status_code == 404
    assert (await client.get("/api/sessions", params=rng | {"state": "x"})).status_code == 422


async def test_session_detail(client, conn):
    e1 = await make_event(conn, ts=NOW - timedelta(seconds=30), path="/pricing", status=403)
    e2 = await make_event(conn, ts=NOW - timedelta(seconds=20), path="/pricing", status=403)
    e3 = await make_event(conn, ts=NOW - timedelta(seconds=5), path="/signup", status=200)
    await make_session(
        conn,
        session_id="sx",
        open=True,
        requests=3,
        retries=1,
        has_retry=True,
        gaps=["no CDN log: edge blocks unknown"],
        status_counts={"200": 1, "403": 2},
        shared_ip=True,
        confidence="low",
    )
    for i, e in enumerate((e1, e2, e3), start=1):
        await make_session_event(conn, session_id="sx", event_id=e["id"], event_ts=e["ts"], seq=i)
    await make_recommendation(conn, evidence={"sessions": ["sx"], "events": []})
    body = (await client.get("/api/sessions/sx")).json()
    assert body["session"]["state"] == "in_progress"
    assert body["facts"]["status_counts"] == {"200": 1, "403": 2}
    assert body["facts_label"] == "observed"
    assert body["grouping"]["label"] == "inferred"
    assert body["outcome"]["label"] == "unknown" and "Unknown" in body["outcome"]["text"]
    steps = body["steps"]
    assert [s["path"] for s in steps] == ["/pricing", "/pricing", "/signup"]
    assert steps[0]["delta_seconds"] is None and steps[1]["delta_seconds"] == 10.0
    assert "retry" in steps[1]["flags"] and "key_page" in steps[0]["flags"]
    assert "conversion_page" in steps[2]["flags"]
    texts = {g["text"]: g["label"] for g in body["gaps"]}
    assert texts["no CDN log: edge blocks unknown"] == "unknown"
    assert any("shared IP" in t for t in texts)
    assert body["confidence_reason"]["text"].startswith("Shared IP")
    assert len(body["recommendations"]) == 1


async def test_session_404(client):
    r = await client.get("/api/sessions/nope")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "session_not_found"
