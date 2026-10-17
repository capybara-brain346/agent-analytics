from datetime import UTC, datetime, timedelta

from tests.factories import make_alert, make_pipeline_run


def fresh(minutes: float) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


async def test_health_ok(client, conn, config_dir):
    for lane in ("fast", "slow"):
        await make_pipeline_run(conn, lane=lane, finished_at=fresh(1), started_at=fresh(2))
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["healthy"] is True
    assert {(x["site_id"], x["lane"], x["healthy"]) for x in body["lanes"]} == {
        ("example", "fast", True),
        ("example", "slow", True),
    }
    assert body["alerts"] == []


async def test_health_stale_fast_lane_is_503(client, conn, config_dir):
    await make_pipeline_run(conn, lane="fast", finished_at=fresh(30), started_at=fresh(31))
    await make_pipeline_run(conn, lane="slow", finished_at=fresh(30), started_at=fresh(31))
    await make_alert(conn, kind="failed_runs", source=None)
    resp = await client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["healthy"] is False
    by_lane = {x["lane"]: x["healthy"] for x in body["lanes"]}
    assert by_lane == {"fast": False, "slow": True}
    assert body["alerts"][0]["kind"] == "failed_runs"


async def test_health_never_ran_is_unhealthy(client, config_dir):
    resp = await client.get("/health")
    assert resp.status_code == 503
    assert all(x["last_success"] is None and not x["healthy"] for x in resp.json()["lanes"])


async def test_livez(client):
    assert (await client.get("/livez")).json() == {"status": "ok"}


async def test_health_uses_latest_success_not_a_scan(client, conn, config_dir):
    for minutes in (500, 400, 3):
        await make_pipeline_run(
            conn, lane="fast", finished_at=fresh(minutes), started_at=fresh(minutes + 1)
        )
    await make_pipeline_run(conn, lane="slow", finished_at=fresh(2), started_at=fresh(3))
    await make_pipeline_run(
        conn, lane="fast", status="failed", finished_at=fresh(0), started_at=fresh(1)
    )
    await make_pipeline_run(conn, site_id="ghost", lane="fast", finished_at=fresh(1))
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert {x["site_id"] for x in resp.json()["lanes"]} == {"example"}
