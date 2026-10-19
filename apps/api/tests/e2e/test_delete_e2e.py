import gzip
from datetime import timedelta

from src.models.domain import Lane
from src.services import pipeline, verify
from tests.e2e.test_pipeline_e2e import (
    AUTH,
    CDN,
    CHROME_IP,
    ORIGIN,
    FakeResolver,
    origin_line,
    rows,
)
from tests.factories import CHROME_UA, GPTBOT_IP, GPTBOT_UA, NOW

SESSION_IPS = (
    "select host(client_ip) as ip from sessions union all select host(client_ip) from open_sessions"
)


async def fast(inbox, at):
    result = await pipeline.run_lane(
        "example", Lane.FAST, now=at, inbox=inbox, resolver=FakeResolver()
    )
    assert result.status == "success", (result.failed_step, result.error)
    return result


async def test_delete_cdn_file_restores_origin_lines_and_rebuilds_views(client, conn, inbox):
    cdn_body = gzip.compress("\n".join(CDN).encode())
    r = await client.post(
        "/ingest", params={"site": "example", "source": "cdn"}, content=cdn_body, headers=AUTH
    )
    cdn_id = r.json()["file_id"]
    r = await client.post(
        "/ingest",
        params={"site": "example", "source": "origin"},
        content="\n".join(ORIGIN).encode(),
        headers=AUTH,
    )
    origin_id = r.json()["file_id"]
    await verify.download_snapshots(conn)
    await fast(inbox, NOW)
    await fast(inbox, NOW + timedelta(minutes=11))
    assert len(await rows(conn, "select 1 from events where source = 'paired'")) == 4

    # The paired rows hold the origin lines: they go with the CDN file, so the origin file is
    # read again. The views are built again from the events that remain.
    r = await client.delete(f"/api/imports/{cdn_id}")
    assert r.status_code == 200, r.text
    assert r.json()["files_reimported"] == [origin_id]
    assert r.json()["events_deleted"] == len(CDN)
    assert len(inbox.objects) == 1
    await fast(inbox, NOW + timedelta(minutes=12))
    await fast(inbox, NOW + timedelta(minutes=23))

    events = await rows(conn, "select * from events")
    assert sorted(e["source"] for e in events) == ["origin"] * len(ORIGIN)
    assert all(e["in_views"] for e in events)
    [gpt] = await rows(
        conn,
        "select requests, status_counts from"
        " (select * from sessions union all select * from open_sessions) s"
        f" where host(client_ip) = '{GPTBOT_IP}'",
    )
    assert (gpt["requests"], gpt["status_counts"]) == (1, {"200": 1})
    assert await rows(conn, "select 1 from page_stats where n_403 > 0") == []

    # The file row is gone, so the same file is accepted again (not a duplicate).
    r = await client.post(
        "/api/imports/upload", params={"site": "example", "source": "cdn"}, content=cdn_body
    )
    assert r.status_code == 202 and r.json()["duplicate"] is False
    assert (await client.delete(f"/api/imports/{cdn_id}")).status_code == 404


async def test_delete_removes_sessions_of_clients_without_new_events(client, conn, inbox):
    # The incremental views only rebuild clients that get new events. The deleted file's client
    # gets none, so only the full rebuild removes its session.
    gpt = "\n".join(
        origin_line(i, f"g{i}", GPTBOT_IP, GPTBOT_UA, "/pricing", 200) for i in range(3)
    )
    chrome = origin_line(5, "c0", CHROME_IP, CHROME_UA, "/signup", 200)
    ids = []
    for body in (gpt, chrome):
        r = await client.post(
            "/ingest", params={"site": "example", "source": "origin"}, content=body, headers=AUTH
        )
        ids.append(r.json()["file_id"])
    await verify.download_snapshots(conn)
    await fast(inbox, NOW)
    await fast(inbox, NOW + timedelta(minutes=11))
    assert sorted(s["ip"] for s in await rows(conn, SESSION_IPS)) == sorted([GPTBOT_IP, CHROME_IP])

    r = await client.delete(f"/api/imports/{ids[0]}")
    assert r.status_code == 200 and r.json()["files_reimported"] == []
    await fast(inbox, NOW + timedelta(minutes=12))
    assert [s["ip"] for s in await rows(conn, SESSION_IPS)] == [CHROME_IP]
    assert await rows(conn, "select 1 from agents where claimed_agent = 'gptbot'") == []
