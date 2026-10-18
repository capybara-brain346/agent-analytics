from datetime import timedelta

from src.models.domain import Lane
from src.services.pipeline import worker
from src.store import locks
from tests.factories import make_pipeline_run


async def status_of(conn, run_id):
    cur = await conn.execute(
        "select status, error, finished_at from pipeline_runs where id = %s", [run_id]
    )
    return await cur.fetchone()


async def test_crashed_run_is_closed_as_failed(conn, pool, config_dir, now):
    old = await make_pipeline_run(
        conn, status="running", finished_at=None, started_at=now - timedelta(hours=2)
    )
    fresh = await make_pipeline_run(
        conn, status="running", finished_at=None, lane="slow", started_at=now - timedelta(minutes=2)
    )
    await worker.close_stale_runs(now)
    status, error, finished = await status_of(conn, old["id"])
    assert (status, error) == ("failed", "worker stopped") and finished is not None
    assert (await status_of(conn, fresh["id"]))[0] == "running"


async def test_running_run_with_taken_lock_is_left_alone(conn, pool, config_dir, now):
    run = await make_pipeline_run(
        conn, status="running", finished_at=None, started_at=now - timedelta(hours=2)
    )
    async with locks.site_lane_lock(conn, "example", Lane.FAST) as got:
        assert got
        await worker.close_stale_runs(now)
        assert (await status_of(conn, run["id"]))[0] == "running"
    await worker.close_stale_runs(now)
    assert (await status_of(conn, run["id"]))[0] == "failed"


async def test_tick_closes_stale_runs(conn, pool, config_dir, now, monkeypatch):
    async def fake_run_lane(*a, **k):
        return None

    monkeypatch.setattr(worker.service, "run_lane", fake_run_lane)
    run = await make_pipeline_run(
        conn, status="running", finished_at=None, started_at=now - timedelta(hours=2)
    )
    await worker.tick(now=now, maintenance=False)
    assert (await status_of(conn, run["id"]))[0] == "failed"
