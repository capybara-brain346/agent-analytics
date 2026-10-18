from datetime import timedelta

from tests.factories import NOW, make_recommendation, make_recommendation_run


async def test_no_run_yet(client):
    body = (await client.get("/api/recommendations")).json()
    assert body["run"] is None and body["empty_reason"] == "no_run"
    assert body["items"] == [] and body["gone"] == []


async def test_unknown_run_404(client):
    r = await client.get("/api/recommendations", params={"run": 999})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "run_not_found"


async def test_latest_run_list_header_and_sections(client, conn):
    old = await make_recommendation_run(conn, started_at=NOW - timedelta(hours=6))
    await make_recommendation(conn, run_id=old["id"], stable_id="a", change="new")
    run = await make_recommendation_run(conn)
    await make_recommendation(
        conn,
        run_id=run["id"],
        stable_id="a",
        rank=1,
        change="open",
        factor_reasons={"impact": "/pricing is a key page"},
    )
    await make_recommendation(
        conn,
        run_id=run["id"],
        stable_id="b",
        rank=2,
        change="new",
        pattern="P3",
        score=9,
        confidence="medium",
    )
    await make_recommendation(conn, run_id=run["id"], stable_id="c", rank=None, change="gone")
    body = (await client.get("/api/recommendations")).json()
    hdr = body["run"]
    assert hdr["id"] == run["id"] and hdr["compared_with_run_id"] == old["id"]
    assert hdr["counts"] == {"new": 1, "open": 1, "gone": 1, "total": 3}
    assert hdr["rule_version"] == "1" and hdr["window_size"] == "6h"
    assert [i["stable_id"] for i in body["items"]] == ["a", "b"]
    assert [i["stable_id"] for i in body["gone"]] == ["c"]
    first = body["items"][0]
    assert first["priority"]["formula"] == "18 = 3 x 2 x 3 x 1.0"
    assert first["priority"]["factors"]["impact"] == {"value": 3.0, "why": "/pricing is a key page"}
    assert first["pattern_name"] == "Blocked access"
    # filters
    body = (await client.get("/api/recommendations", params={"pattern": "P3"})).json()
    assert [i["stable_id"] for i in body["items"]] == ["b"]
    body = (await client.get("/api/recommendations", params={"confidence": "high"})).json()
    assert [i["stable_id"] for i in body["items"]] == ["a"]
    body = (await client.get("/api/recommendations", params={"change": "new"})).json()
    assert [i["stable_id"] for i in body["items"]] == ["b"]
    # old run kept as it was
    body = (await client.get("/api/recommendations", params={"run": old["id"]})).json()
    assert [i["stable_id"] for i in body["items"]] == ["a"]
    assert (await client.get("/api/recommendations", params={"pattern": "P9"})).status_code == 422


async def test_run_without_candidates(client, conn):
    await make_recommendation_run(conn)
    body = (await client.get("/api/recommendations")).json()
    assert body["empty_reason"] == "no_candidates"


async def test_detail(client, conn):
    old = await make_recommendation_run(conn, started_at=NOW - timedelta(hours=6))
    await make_recommendation(
        conn, run_id=old["id"], stable_id="a", change="new", journey_id="signup"
    )
    run = await make_recommendation_run(conn)
    rec = await make_recommendation(
        conn,
        run_id=run["id"],
        stable_id="a",
        change="open",
        journey_id="signup",
        potential_issue="Maybe blocked",
        next_action="Simulate",
        bundle={"status": {"2": 403}},
        evidence={"sessions": ["s-1", "s-2"], "events": [4, 5]},
        sessions_count=2,
        events_count=2,
    )
    other = await make_recommendation(
        conn, run_id=run["id"], stable_id="z", journey_id="signup", rank=2
    )
    body = (await client.get(f"/api/recommendations/{rec['id']}")).json()
    assert body["evidence"]["session_ids"] == ["s-1", "s-2"]
    assert body["evidence"]["event_ids"] == [4, 5]
    assert body["potential_issue"] == {"text": "Maybe blocked", "label": "inferred"}
    assert body["next_action"]["label"] == "unknown"
    assert body["reason"]["label"] == "observed"
    assert body["fact_bundle"] == {"status": {"2": 403}}
    assert body["first_seen_run_id"] == old["id"]
    assert [h["run_id"] for h in body["history"]] == [old["id"], run["id"]]
    assert [r["id"] for r in body["related"]] == [other["id"]]
    assert body["text_source_note"].startswith("Template text")
    assert body["run"]["id"] == run["id"]


async def test_detail_404_and_422(client):
    assert (await client.get("/api/recommendations/12345")).status_code == 404
    assert (await client.get("/api/recommendations/abc")).status_code == 422


async def test_run_history(client, conn):
    r1 = await make_recommendation_run(conn, started_at=NOW - timedelta(hours=6))
    r2 = await make_recommendation_run(conn)
    await make_recommendation(conn, run_id=r2["id"], stable_id="a")
    body = (await client.get("/api/recommendations/runs")).json()
    assert [r["id"] for r in body["items"]] == [r2["id"], r1["id"]]
    assert body["items"][0]["counts"]["total"] == 1
    assert body["page"] == {"limit": 50, "offset": 0, "total": 2, "next_offset": None}
    body = (await client.get("/api/recommendations/runs", params={"limit": 1})).json()
    assert body["page"]["next_offset"] == 1


async def test_generate_ok_and_locked(client, conn, monkeypatch):
    from src.services import pipeline

    calls = []

    async def ok(site, window):
        calls.append((site, window))
        await make_recommendation_run(conn)

    monkeypatch.setattr(pipeline, "run_recommendations", ok)
    r = await client.post("/api/recommendations/generate", params={"window": "12h"})
    assert r.status_code == 200 and calls == [("example", "12h")]
    assert r.json()["run"]["id"] > 0

    async def locked(site, window):
        raise pipeline.LockTaken(site)

    monkeypatch.setattr(pipeline, "run_recommendations", locked)
    r = await client.post("/api/recommendations/generate")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "lock_taken"

    async def boom(site, window):
        raise RuntimeError("verify failed")

    monkeypatch.setattr(pipeline, "run_recommendations", boom)
    r = await client.post("/api/recommendations/generate")
    assert r.status_code == 500 and r.json()["detail"]["code"] == "run_failed"

    class LockInName(Exception):
        pass

    async def other_lock(site, window):
        raise LockInName()

    monkeypatch.setattr(pipeline, "run_recommendations", other_lock)
    r = await client.post("/api/recommendations/generate")
    assert r.status_code == 500

    async def failed(site, window):
        raise pipeline.RunFailed("run-42", "recommendations", "boom")

    monkeypatch.setattr(pipeline, "run_recommendations", failed)
    r = await client.post("/api/recommendations/generate")
    detail = r.json()["detail"]
    assert r.status_code == 500 and detail["code"] == "run_failed" and "run-42" in detail["message"]
    assert (
        await client.post("/api/recommendations/generate", params={"window": "x"})
    ).status_code == 422
