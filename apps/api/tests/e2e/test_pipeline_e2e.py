import gzip
import json
from datetime import timedelta

import pytest
from psycopg.rows import dict_row

from src.config import get_settings
from src.models.domain import Lane
from src.routes.ingest import inbox_dependency
from src.services import ingest, pipeline, verify
from tests.factories import CHROME_UA, GPTBOT_IP, GPTBOT_UA, NOW
from tests.fakes import MemoryInbox

AUTH = {"Authorization": "Bearer dev-token"}
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
FAKE_GOOGLEBOT_IP = "203.0.113.9"
CHROME_IP = "198.51.100.7"
BASE = NOW - timedelta(minutes=40)


class FakeResolver:
    # The fake Googlebot IP has a PTR name outside googlebot.com and google.com.
    async def ptr(self, ip):
        return {FAKE_GOOGLEBOT_IP: ["host.evil.example.net"]}.get(ip, [])

    async def addresses(self, host):
        return []


def cdn_line(sec, rid, ip, ua, path, status, score):
    return json.dumps(
        {
            "request_id": rid,
            "timestamp": (BASE + timedelta(seconds=sec)).isoformat(),
            "client_ip": ip,
            "method": "GET",
            "path": path,
            "status": status,
            "bytes": 2048,
            "user_agent": ua,
            "bot_score": score,
        }
    )


def origin_line(sec, rid, ip, ua, path, status):
    t = (BASE + timedelta(seconds=sec)).strftime("%d/%b/%Y:%H:%M:%S +0000")
    return f'{ip} - - [{t}] "GET {path} HTTP/1.1" {status} 2048 "-" "{ua}" "{rid}" 0.020'


# Paired: GPTBot /pricing, fake Googlebot /docs/api, Chrome /pricing and /signup.
# CDN only (blocked at the edge): six GPTBot 403 on /pricing.
CDN = [
    cdn_line(0, "g0", GPTBOT_IP, GPTBOT_UA, "/pricing", 200, 5),
    cdn_line(10, "s0", FAKE_GOOGLEBOT_IP, GOOGLEBOT_UA, "/docs/api", 200, 5),
    cdn_line(20, "c0", CHROME_IP, CHROME_UA, "/pricing", 200, 90),
    cdn_line(30, "c1", CHROME_IP, CHROME_UA, "/signup", 200, 90),
    *[cdn_line(60 + i, f"b{i}", GPTBOT_IP, GPTBOT_UA, "/pricing", 403, 5) for i in range(6)],
]
ORIGIN = [
    origin_line(0, "g0", GPTBOT_IP, GPTBOT_UA, "/pricing", 200),
    origin_line(10, "s0", FAKE_GOOGLEBOT_IP, GOOGLEBOT_UA, "/docs/api", 200),
    origin_line(20, "c0", CHROME_IP, CHROME_UA, "/pricing", 200),
    origin_line(30, "c1", CHROME_IP, CHROME_UA, "/signup", 200),
]


@pytest.fixture
def inbox(config_dir, client, monkeypatch) -> MemoryInbox:
    monkeypatch.setenv("OFFLINE", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    ingest.reset_limits()
    memory = MemoryInbox()
    app = client._transport.app
    app.dependency_overrides[inbox_dependency] = lambda: memory
    yield memory
    app.dependency_overrides.clear()
    ingest.reset_limits()


async def rows(conn, sql):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql)
        return await cur.fetchall()


async def test_two_files_to_dashboard(client, conn, inbox):
    # 1. Ingest: a gzip CDN file and a plain origin file.
    cdn_body = gzip.compress("\n".join(CDN).encode())
    r = await client.post(
        "/ingest",
        params={"site": "example", "source": "cdn"},
        content=cdn_body,
        headers=AUTH | {"Content-Encoding": "gzip"},
    )
    assert r.status_code == 202, r.text
    r = await client.post(
        "/ingest",
        params={"site": "example", "source": "origin"},
        content="\n".join(ORIGIN).encode(),
        headers=AUTH,
    )
    assert r.status_code == 202, r.text

    # 2. Fast lane with a fixed clock. The IP lists come from the bundled files (offline).
    await verify.download_snapshots(conn)
    fast = await pipeline.run_lane(
        "example", Lane.FAST, now=NOW, inbox=inbox, resolver=FakeResolver()
    )
    assert fast.status == "success", (fast.failed_step, fast.error)
    assert fast.counts["import"]["files"] == 2
    assert fast.counts["import"]["lines_imported"] == len(CDN) + len(ORIGIN)
    assert fast.counts["pair"]["paired"] == 4
    assert fast.counts["pair"]["single"] == 0  # The wait counts from arrival (1b.6)

    # Ten minutes after the arrival the six CDN-only rows become single.
    fast = await pipeline.run_lane(
        "example",
        Lane.FAST,
        now=NOW + timedelta(minutes=11),
        inbox=inbox,
        resolver=FakeResolver(),
    )
    assert fast.status == "success", (fast.failed_step, fast.error)
    assert fast.counts["pair"]["single"] == 6

    # Pairing: four paired rows, no origin rows left, six CDN-only rows.
    events = await rows(conn, "select * from events order by ts, id")
    assert len(events) == len(CDN)
    assert [e["source"] for e in events].count("paired") == 4
    assert not [e for e in events if e["source"] == "origin"]
    assert all(e["pair_state"] != "pending" for e in events)
    assert all(e["verdict_id"] is not None for e in events)
    assert all(e["in_views"] for e in events)
    paired_gpt = next(e for e in events if e["edge_request_id"] == "g0")
    assert paired_gpt["origin_status"] == 200 and paired_gpt["origin_line_key"]

    # Verify + classify.
    verdicts = {
        v["client_ip"] and str(v["client_ip"]): v
        for v in await rows(conn, "select * from verdicts")
    }
    gpt = verdicts[GPTBOT_IP]
    assert (gpt["verdict"], gpt["method"], gpt["claimed_agent"]) == (
        "VERIFIED",
        "ip_list",
        "gptbot",
    )
    assert gpt["traffic_class"] == 2
    spoof = verdicts[FAKE_GOOGLEBOT_IP]
    assert (spoof["verdict"], spoof["method"]) == ("SPOOFED", "rdns")
    assert spoof["traffic_class"] == 6 and "spoofed" in spoof["flags"]
    human = verdicts[CHROME_IP]
    assert (human["traffic_class"], human["verdict"]) == (5, "UNKNOWN")
    assert all(v["traffic_class"] is not None for v in verdicts.values())

    # Views: sessions and hourly rows.
    sessions = await rows(
        conn,
        "select * from sessions union all select * from open_sessions",
    )
    by_ip = {str(s["client_ip"]): s for s in sessions}
    assert by_ip[GPTBOT_IP]["requests"] == 7 and by_ip[GPTBOT_IP]["status_counts"] == {
        "200": 1,
        "403": 6,
    }
    assert by_ip[CHROME_IP]["reached_conversion"] is True
    assert by_ip[CHROME_IP]["journeys_reached"] == {"signup": 2}
    pricing = await rows(
        conn, "select traffic_class, requests, n_403 from page_stats where path = '/pricing'"
    )
    assert {(p["traffic_class"], p["requests"], p["n_403"]) for p in pricing} == {
        (2, 7, 6),
        (5, 1, 0),
    }
    assert await rows(conn, "select 1 from agents where claimed_agent = 'gptbot'")

    # A second fast run finds nothing to do.
    again = await pipeline.run_lane(
        "example",
        Lane.FAST,
        now=NOW + timedelta(minutes=12),
        inbox=inbox,
        resolver=FakeResolver(),
    )
    assert again.counts["import"]["files"] == 0
    assert again.counts["views"]["clients_recomputed"] == 0

    # 3. Slow lane: recommendations with the template text (LLM off).
    slow = await pipeline.run_lane("example", Lane.SLOW, now=NOW)
    assert slow.status == "success", (slow.failed_step, slow.error)

    # 4. Dashboard API and health.
    window = {
        "from": (NOW - timedelta(hours=6)).isoformat(),
        "to": (NOW + timedelta(hours=1)).isoformat(),
    }
    overview = (await client.get("/api/overview", params=window)).json()
    assert overview["empty"] is False
    classes = {c["traffic_class"]: c for c in overview["traffic_by_class"]}
    assert (
        classes[2]["requests"] == 7 and classes[5]["requests"] == 2 and classes[6]["requests"] == 1
    )
    assert overview["top_recommendations"]

    listed = (await client.get("/api/sessions", params=window)).json()
    assert listed["page"]["total"] == 3
    assert {s["traffic_class"] for s in listed["items"]} == {2, 5, 6}

    recs = (await client.get("/api/recommendations")).json()
    assert recs["run"]["status"] == "success"
    [top] = [i for i in recs["items"] if i["pattern"] == "P2"]
    assert top["target"] == "/pricing" and top["priority"]["score"] == 9
    assert top["priority"]["formula"] == "9 = 3 x 1 x 3 x 1.0"
    assert top["text_source"] == "template"

    health = await client.get("/health")
    assert health.status_code == 200 and health.json()["healthy"] is True
