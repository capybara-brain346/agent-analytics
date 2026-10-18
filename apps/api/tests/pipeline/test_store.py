from datetime import timedelta

from psycopg import AsyncConnection

from src.models.domain import AlertKind, Lane, RunStatus
from src.store import alerts as alerts_store
from src.store import locks, runs, work
from tests.factories import make_alert, make_pipeline_run, make_site_work


async def test_lock_prevents_second_holder(conn: AsyncConnection, db_url: str):
    async with await AsyncConnection.connect(db_url, autocommit=True) as other:
        async with locks.site_lane_lock(conn, "example", Lane.FAST) as got:
            assert got is True
            async with locks.site_lane_lock(other, "example", Lane.FAST) as second:
                assert second is False
            async with locks.site_lane_lock(other, "example", Lane.SLOW) as other_lane:
                assert other_lane is True
            async with locks.site_lane_lock(other, "bank", Lane.FAST) as other_site:
                assert other_site is True
        async with locks.site_lane_lock(other, "example", Lane.FAST) as again:
            assert again is True


async def test_run_start_finish_and_last_success(conn: AsyncConnection, now):
    run_id = await runs.start_run(conn, "example", Lane.FAST)
    rows = await runs.recent_runs(conn, site_id="example")
    assert rows[0]["status"] == "running"
    await runs.finish_run(conn, run_id, RunStatus.SUCCESS, counts={"import": {"files": 2}})
    row = (await runs.recent_runs(conn, site_id="example"))[0]
    assert row["status"] == "success"
    assert row["counts"] == {"import": {"files": 2}}
    assert row["finished_at"] is not None
    last = await runs.last_success_by_lane(conn, ["example"])
    assert [(r["site_id"], r["lane"]) for r in last] == [("example", "fast"), ("example", "slow")]
    assert last[0]["last_success"] is not None and last[1]["last_success"] is None


async def test_consecutive_failures_resets_on_success(conn: AsyncConnection, now):
    step = timedelta(minutes=1)
    await make_pipeline_run(conn, status="failed", started_at=now - 5 * step)
    await make_pipeline_run(conn, status="success", started_at=now - 4 * step)
    await make_pipeline_run(conn, status="failed", started_at=now - 3 * step)
    await make_pipeline_run(conn, status="failed", started_at=now - 2 * step)
    await make_pipeline_run(conn, status="failed", lane="slow", started_at=now - 2 * step)
    assert await runs.consecutive_failures(conn, "example", Lane.FAST) == 2
    assert await runs.consecutive_failures(conn, "example", Lane.SLOW) == 1
    assert await runs.consecutive_failures(conn, "other", Lane.FAST) == 0


async def test_fair_turns_oldest_first(conn: AsyncConnection, now):
    await make_site_work(conn, site_id="a", last_run_at=now - timedelta(minutes=1))
    await make_site_work(conn, site_id="b", last_run_at=None)
    await make_site_work(conn, site_id="c", last_run_at=now - timedelta(minutes=5))
    await make_site_work(conn, site_id="slow-only", lane="slow")
    order = []
    while (site := await work.take_due_site(conn, Lane.FAST, now)) is not None:
        order.append(site)
    assert order == ["b", "c", "a"]


async def test_take_due_site_filters_configured_sites(conn: AsyncConnection, now):
    await work.ensure_site_work(conn, ["a", "gone"])
    assert await work.take_due_site(conn, Lane.FAST, now, ["a"]) == "a"
    assert await work.take_due_site(conn, Lane.FAST, now, ["a"]) is None


async def test_skip_locked_two_connections(conn: AsyncConnection, db_url: str, now):
    await work.ensure_site_work(conn, ["a", "b"])
    async with await AsyncConnection.connect(db_url) as other:
        first = await work.take_due_site(other, Lane.FAST, now)
        second = await work.take_due_site(conn, Lane.FAST, now)
        assert {first, second} == {"a", "b"}
        await other.rollback()


async def test_slow_lane_due_by_next_due_at(conn: AsyncConnection, now):
    await make_site_work(conn, site_id="a", lane="slow", next_due_at=now + timedelta(hours=1))
    await make_site_work(conn, site_id="b", lane="slow", next_due_at=now - timedelta(minutes=1))
    await make_site_work(conn, site_id="c", lane="slow", next_due_at=None)
    taken = []
    while (site := await work.take_due_site(conn, Lane.SLOW, now)) is not None:
        taken.append(site)
    assert sorted(taken) == ["b", "c"]
    row = await (
        await conn.execute("select next_due_at from site_work where site_id='b' and lane='slow'")
    ).fetchone()
    assert row[0] > now


async def test_record_run_counts_failures(conn: AsyncConnection):
    await work.record_run(conn, "example", Lane.FAST, success=False)
    await work.record_run(conn, "example", Lane.FAST, success=False)
    cur = await conn.execute("select consecutive_failures, last_success_at from site_work")
    assert await cur.fetchone() == (2, None)
    await work.record_run(conn, "example", Lane.FAST, success=True)
    cur = await conn.execute("select consecutive_failures, last_success_at from site_work")
    failures, success_at = await cur.fetchone()
    assert failures == 0 and success_at is not None


async def test_alert_raise_is_idempotent_and_resolves(conn: AsyncConnection):
    first = await alerts_store.raise_alert(conn, "example", AlertKind.NO_DATA, "cdn", "m")
    again = await alerts_store.raise_alert(conn, "example", AlertKind.NO_DATA, "cdn", "m")
    other = await alerts_store.raise_alert(conn, "example", AlertKind.NO_DATA, "origin", "m")
    assert first is not None and again is None and other is not None
    assert len(await alerts_store.list_alerts(conn, open_only=True)) == 2
    assert await alerts_store.resolve_alert(conn, "example", AlertKind.NO_DATA, "cdn") is True
    assert await alerts_store.resolve_alert(conn, "example", AlertKind.NO_DATA, "cdn") is False
    open_rows = await alerts_store.list_alerts(conn, site_id="example", open_only=True)
    assert [r["source"] for r in open_rows] == ["origin"]
    assert len(await alerts_store.list_alerts(conn)) == 2
    await make_alert(conn, kind="failed_runs", source=None)
    assert await alerts_store.raise_alert(conn, "example", AlertKind.FAILED_RUNS, None, "m") is None
