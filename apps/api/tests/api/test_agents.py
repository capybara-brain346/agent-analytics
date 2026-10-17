from datetime import timedelta

from tests.factories import NOW, make_agent, make_session, make_verdict


async def test_agents_empty(client, rng):
    assert (await client.get("/api/agents", params=rng)).json() == []


async def test_agents_list_sums_hours_and_counts_sessions_from_tables(client, rng, conn):
    h = NOW.replace(minute=0)
    await make_agent(conn, hour=h, requests=10, first_seen=NOW - timedelta(hours=1), last_seen=h)
    await make_agent(
        conn,
        hour=h - timedelta(hours=1),
        requests=5,
        sessions=9,
        top_paths=["/pricing", "/a"],
        first_seen=NOW - timedelta(hours=2),
        last_seen=NOW - timedelta(hours=1),
    )
    await make_agent(
        conn,
        claimed_agent="unknown:browser",
        traffic_class=5,
        verification="UNKNOWN",
        confidence="medium",
        requests=3,
    )
    # one session spanning both hours: distinct sessions = 1, not 2 + 9
    await make_session(conn, session_id="a", pages_in_order=["/pricing", "/products"])
    await make_session(conn, session_id="b", open=True, pages_in_order=["/pricing", "/docs"])
    body = (await client.get("/api/agents", params=rng)).json()
    gpt = body[0]
    assert gpt["agent_id"] == "gptbot" and gpt["vendor"] == "OpenAI"
    assert gpt["requests"] == 15
    assert gpt["sessions"] == 2
    assert gpt["distinct_pages"] == 3
    assert gpt["first_seen"].startswith("2026-10-17T10:00")
    assert gpt["common_paths"][0] == "/pricing"
    assert gpt["verification"] == "VERIFIED" and "Verified" in gpt["verification_note"]
    unknown = body[1]
    assert unknown["agent_id"] == "unknown:browser" and unknown["vendor"] is None
    assert unknown["verification_note"] == "Claims to be unknown:browser, unverified"

    async def names(**p):
        return [a["agent_id"] for a in (await client.get("/api/agents", params=rng | p)).json()]

    assert await names(**{"class": "5"}) == ["unknown:browser"]
    assert await names(verification="VERIFIED") == ["gptbot"]
    assert await names(q="GPT") == ["gptbot"]
    assert await names(q="zzz") == []
    r = await client.get("/api/agents", params=rng | {"verification": "NOPE"})
    assert r.status_code == 422


async def test_agent_detail(client, rng, conn, traffic):
    t = await traffic()
    await make_agent(conn, requests=10)
    await make_verdict(
        conn,
        verdict="SPOOFED",
        method="ip_list",
        evidence="not in snapshot",
        client_ip="9.9.9.9",
        checked_at=NOW + timedelta(minutes=1),
    )
    await make_session(conn, session_id="s-1", shared_ip=True)
    body = (await client.get("/api/agents/gptbot", params=rng)).json()
    assert body["agent"]["name"] == "gptbot" and body["agent"]["requests"] == 10
    hist = body["verdict_history"]
    assert [v["verdict"] for v in hist][0] == "SPOOFED"  # newest first
    assert hist[-1]["id"] == t["gpt"]["id"]
    assert hist[-1]["events_link"].endswith(f"verdict_id={t['gpt']['id']}")
    assert body["why_this_class"]["rule_id"] == "R3"
    assert body["why_this_class"]["inputs"]["verdict"] == "VERIFIED"
    assert {k["client_ip"] for k in body["client_keys"]} == {"20.171.1.5", "9.9.9.9"}
    assert body["top_paths"][0] == {"path": "/pricing", "requests": 2}
    assert {m["status"]: m["requests"] for m in body["status_mix"]} == {200: 2, 403: 1}
    assert body["activity"][0]["requests"] == 10
    assert body["sessions"][0]["session_id"] == "s-1"


async def test_agent_404(client, rng):
    r = await client.get("/api/agents/nobody", params=rng)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "agent_not_found"
