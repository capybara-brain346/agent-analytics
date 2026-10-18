import pytest
from psycopg import AsyncConnection

from src.models.domain import Lane
from src.services import pipeline
from src.services.pipeline import service
from src.store import locks


def recording_steps(calls: list, fail_at: str | None = None, raise_error: bool = False):
    def make(name: str):
        async def step(conn: AsyncConnection, site_id: str) -> dict:
            calls.append((name, site_id))
            await conn.execute("create table if not exists step_marks (name text)")
            await conn.execute("insert into step_marks values (%s)", [name])
            if name == fail_at:
                raise RuntimeError("boom")
            return {"items": 1}

        return step

    return [(name, make(name)) for name in ("import", "pair", "verify")]


async def marks(conn: AsyncConnection) -> list[str]:
    cur = await conn.execute("select name from step_marks order by name")
    return [r[0] for r in await cur.fetchall()]


async def test_success_run_records_counts(conn, pool):
    calls = []
    result = await pipeline.run_lane("example", Lane.FAST, steps=recording_steps(calls))
    assert result.status == "success"
    assert [c[0] for c in calls] == ["import", "pair", "verify"]
    cur = await conn.execute(
        "select status, finished_at is not null, counts from pipeline_runs where id = %s",
        [result.run_id],
    )
    status, finished, counts = await cur.fetchone()
    assert status == "success" and finished
    assert counts == {"import": {"items": 1}, "pair": {"items": 1}, "verify": {"items": 1}}
    cur = await conn.execute("select consecutive_failures, last_success_at from site_work")
    failures, success_at = await cur.fetchone()
    assert failures == 0 and success_at is not None


async def test_failed_step_stops_and_keeps_earlier_writes(conn, pool):
    calls = []
    result = await pipeline.run_lane(
        "example", Lane.FAST, steps=recording_steps(calls, fail_at="pair")
    )
    assert result.status == "failed" and result.failed_step == "pair"
    assert [c[0] for c in calls] == ["import", "pair"]
    assert await marks(conn) == ["import"]
    cur = await conn.execute("select status, failed_step, error, counts from pipeline_runs")
    status, step, error, counts = await cur.fetchone()
    assert (status, step) == ("failed", "pair")
    assert "boom" in error
    assert counts == {"import": {"items": 1}}
    cur = await conn.execute("select consecutive_failures from site_work")
    assert (await cur.fetchone())[0] == 1


async def test_lock_taken_skips_run(conn, pool):
    calls = []
    async with locks.site_lane_lock(conn, "example", Lane.FAST) as got:
        assert got
        result = await pipeline.run_lane("example", Lane.FAST, steps=recording_steps(calls))
    assert result is None and calls == []
    cur = await conn.execute("select count(*) from pipeline_runs")
    assert (await cur.fetchone())[0] == 0
    again = await pipeline.run_lane("example", Lane.FAST, steps=recording_steps(calls))
    assert again.status == "success"


async def test_three_failures_raise_alert_and_success_resolves(conn, pool):
    for _ in range(3):
        await pipeline.run_lane("example", Lane.FAST, steps=recording_steps([], fail_at="import"))
    cur = await conn.execute("select kind, source, resolved_at from alerts")
    assert await cur.fetchall() == [("failed_runs", None, None)]
    await pipeline.run_lane("example", Lane.FAST, steps=recording_steps([]))
    cur = await conn.execute("select resolved_at is not null from alerts")
    assert await cur.fetchall() == [(True,)]


async def test_two_failures_raise_no_alert(conn, pool):
    for _ in range(2):
        await pipeline.run_lane("example", Lane.FAST, steps=recording_steps([], fail_at="import"))
    cur = await conn.execute("select count(*) from alerts")
    assert (await cur.fetchone())[0] == 0


async def test_slow_lane_calls_recommendations(conn, pool, monkeypatch, settings):
    seen = []

    async def fake_generate(c, site_id, window):
        seen.append((site_id, window))
        return "rec-run-1"

    monkeypatch.setattr(service.recommendations, "generate", fake_generate)
    result = await pipeline.run_lane("example", Lane.SLOW)
    assert result.status == "success"
    assert seen == [("example", settings.recommendation_window)]
    cur = await conn.execute("select lane, counts from pipeline_runs")
    assert await cur.fetchall() == [("slow", {"recommendations": {"run_id": "rec-run-1"}})]


async def test_run_recommendations_returns_id_and_raises_on_lock(conn, pool, monkeypatch):
    async def fake_generate(c, site_id, window):
        return f"rec-{window}"

    monkeypatch.setattr(service.recommendations, "generate", fake_generate)
    assert await pipeline.run_recommendations("example", "14d") == "rec-14d"
    async with locks.site_lane_lock(conn, "example", Lane.SLOW):
        with pytest.raises(pipeline.LockTaken):
            await pipeline.run_recommendations("example", "6h")


async def test_run_recommendations_failure_raises(conn, pool, monkeypatch):
    async def bad(c, site_id, window):
        raise ValueError("bad window")

    monkeypatch.setattr(service.recommendations, "generate", bad)
    with pytest.raises(pipeline.RunFailed):
        await pipeline.run_recommendations("example", "zz")
    cur = await conn.execute("select status, failed_step from pipeline_runs")
    assert await cur.fetchall() == [("failed", "recommendations")]


def test_slow_interval_from_window():
    from datetime import timedelta

    assert pipeline.slow_interval("6h") == timedelta(hours=6)
    assert pipeline.slow_interval("14d") == timedelta(days=14)
    assert pipeline.slow_interval("nonsense") == timedelta(hours=6)
