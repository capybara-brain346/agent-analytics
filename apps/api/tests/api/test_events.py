from datetime import timedelta

from tests.factories import (
    NOW,
    make_import_file,
    make_recommendation,
    make_session,
    make_session_event,
)


async def test_events_empty(client, rng):
    body = (await client.get("/api/events", params=rng)).json()
    assert body["items"] == []
    assert body["page"]["total"] == 0


async def test_events_list_filters_paging(client, rng, traffic):
    t = await traffic()
    body = (await client.get("/api/events", params=rng)).json()
    assert body["page"]["total"] == 5  # pending row hidden
    assert [e["path"] for e in body["items"]][:2] == ["/pricing", "/pricing"]
    assert body["items"][0]["class_name"] == "Known AI crawler"
    assert body["items"][0]["claimed_agent"] == "gptbot"

    def ids(body):
        return [e["id"] for e in body["items"]]

    async def get(**p):
        return (await client.get("/api/events", params=rng | p)).json()

    assert (await get(**{"class": "5"}))["page"]["total"] == 1
    assert (await get(agent="gptbot"))["page"]["total"] == 3
    assert (await get(path="DOCS"))["page"]["total"] == 1
    assert (await get(status="403"))["page"]["total"] == 1
    assert (await get(status="4xx"))["page"]["total"] == 1
    assert (await get(status="403,500"))["page"]["total"] == 2
    assert (await get(verdict="UNKNOWN"))["page"]["total"] == 1
    assert (await get(confidence="medium"))["page"]["total"] == 1
    assert (await get(source="cdn"))["page"]["total"] == 1
    assert (await get(client_key=t["browser"]["client_key"]))["page"]["total"] == 1
    assert (await get(verdict_id=t["gpt"]["id"]))["page"]["total"] == 3
    page1 = await get(limit=2)
    page2 = await get(limit=2, offset=page1["page"]["next_offset"])
    assert page1["page"]["next_offset"] == 2 and len(page2["items"]) == 2
    assert not set(ids(page1)) & set(ids(page2))
    narrow = (
        await client.get(
            "/api/events",
            params={
                "from": (NOW - timedelta(minutes=1)).isoformat(),
                "to": (NOW + timedelta(hours=1)).isoformat(),
            },
        )
    ).json()
    assert narrow["page"]["total"] == 1


async def test_events_filter_session_and_file(client, rng, traffic, conn):
    t = await traffic()
    f = await make_import_file(conn)
    from tests.factories import make_event

    inside = await make_event(conn, ts=NOW - timedelta(minutes=9), file_id=f["id"], path="/in")
    await make_session(conn, session_id="s-9")
    await make_session_event(
        conn, session_id="s-9", event_id=inside["id"], event_ts=inside["ts"], seq=1
    )
    got = (await client.get("/api/events", params=rng | {"session": "s-9"})).json()
    assert [e["id"] for e in got["items"]] == [inside["id"]]
    assert got["items"][0]["session_id"] == "s-9"
    got = (await client.get("/api/events", params=rng | {"import_file": str(f["id"])})).json()
    assert got["page"]["total"] == 1
    assert (
        await client.get("/api/events", params=rng | {"import_file": "nope"})
    ).status_code == 422
    assert t


async def test_events_bad_filter_422(client, rng):
    assert (await client.get("/api/events", params=rng | {"status": "abc"})).status_code == 422
    assert (await client.get("/api/events", params=rng | {"verdict": "MAYBE"})).status_code == 422
    assert (await client.get("/api/events", params=rng | {"source": "x"})).status_code == 422


async def test_event_detail(client, traffic, conn):
    t = await traffic()
    f = await make_import_file(conn, status="success", lines_total=10)
    from tests.factories import make_event

    e = await make_event(
        conn, ts=NOW - timedelta(minutes=8), verdict_id=t["gpt"]["id"], file_id=f["id"], line_no=7
    )
    await make_session(conn, session_id="s-7")
    await make_session_event(conn, session_id="s-7", event_id=e["id"], event_ts=e["ts"], seq=2)
    await make_session_event(
        conn, session_id="s-7", event_id=t["events"][0]["id"], seq=1, event_ts=t["events"][0]["ts"]
    )
    await make_recommendation(conn, evidence={"sessions": [], "events": [e["id"]]})
    body = (await client.get(f"/api/events/{e['id']}")).json()
    assert body["request"]["path"] == "/pricing" and body["request_label"] == "observed"
    assert body["request"]["client_ip"] == "20.171.1.5"
    assert body["source"]["file_id"] == str(f["id"]) and body["source"]["line_no"] == 7
    assert body["verdict"]["verdict"] == "VERIFIED"
    assert body["verdict"]["events_link"].endswith(f"verdict_id={t['gpt']['id']}")
    assert body["classification"]["traffic_class"] == 2
    assert body["classification"]["rule_id"] == "R3"
    assert body["session"] == {"session_id": "s-7", "position": 2, "of": 2}
    assert body["import_file"]["id"] == str(f["id"])
    assert len(body["recommendations"]) == 1


async def test_event_detail_minimal_and_404(client, conn):
    from tests.factories import make_event

    e = await make_event(conn)
    body = (await client.get(f"/api/events/{e['id']}")).json()
    assert body["verdict"] is None and body["session"] is None and body["import_file"] is None
    assert body["classification"] is None
    assert (await client.get("/api/events/99999")).status_code == 404
    assert (await client.get("/api/events/abc")).status_code == 422
