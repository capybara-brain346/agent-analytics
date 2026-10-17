from datetime import timedelta

from src.models.domain import Lane
from src.services import pipeline
from src.services.pipeline import worker
from tests.factories import make_import_file


async def test_tick_runs_each_site_once_per_lane_and_survives_errors(
    conn, pool, config_dir, now, monkeypatch
):
    (config_dir / "sites" / "second.yaml").write_text("site_id: second\nsources: [origin]\n")
    ran = []

    async def fake_run_lane(site_id, lane, pool=None, steps=None):
        ran.append((site_id, lane))
        if site_id == "example" and lane == Lane.FAST:
            raise RuntimeError("one site breaks")

    monkeypatch.setattr(worker.service, "run_lane", fake_run_lane)
    await make_import_file(conn, source="origin", received_at=now)
    await worker.tick(now=now, maintenance=False)
    assert sorted(ran) == [
        ("example", Lane.FAST),
        ("example", Lane.SLOW),
        ("second", Lane.FAST),
        ("second", Lane.SLOW),
    ]
    ran.clear()
    await worker.tick(now=now, maintenance=False)
    assert ran == []


async def test_tick_runs_maintenance_daily(conn, pool, config_dir, now, monkeypatch):
    calls = []

    async def fake_download():
        calls.append("download")

    async def fake_cleanup():
        calls.append("cleanup")
        return {"files_deleted": 0, "partitions_dropped": 0}

    async def fake_run_lane(*a, **k):
        return None

    monkeypatch.setattr(worker.verify, "download_snapshots", fake_download)
    monkeypatch.setattr(worker.cleanup, "run_cleanup", fake_cleanup)
    monkeypatch.setattr(worker.service, "run_lane", fake_run_lane)
    monkeypatch.setattr(worker, "_next_maintenance", {})
    await worker.tick(now=now)
    await worker.tick(now=now)
    assert calls == ["download", "cleanup"]


async def test_tick_end_to_end_with_fake_steps(conn, pool, config_dir, now, monkeypatch):
    seen = []

    async def step(c, site_id):
        seen.append(site_id)
        return {}

    monkeypatch.setattr(worker.service, "FAST_STEPS", (("only", step),))

    async def fake_generate(c, site_id, window):
        return "r"

    monkeypatch.setattr(worker.service.recommendations, "generate", fake_generate)
    await worker.tick(now=now, maintenance=False)
    assert seen == ["example"]
    cur = await conn.execute("select lane, status from pipeline_runs order by lane")
    assert await cur.fetchall() == [("fast", "success"), ("slow", "success")]
    assert pipeline.tick is worker.tick


async def test_tick_reads_cdn_buckets_by_interval(conn, pool, config_dir, now, monkeypatch):
    from datetime import timedelta

    from src.config import get_settings

    (config_dir / "sites" / "example.yaml").write_text(
        "site_id: example\nsources: [cdn]\ncdn_field_map: example\n"
        "cdn_bucket: {bucket: b1, prefix: p/}\n"
    )
    monkeypatch.setenv("BUCKET_READER_ENABLED", "true")
    monkeypatch.setenv("BUCKET_READER_INTERVAL_SECONDS", "60")
    get_settings.cache_clear()
    seen = []

    class FakeReader:
        async def read_new(self, c, target, now=None):
            seen.append((target.site_id, target.bucket, target.prefix, target.source))
            return {}

    async def fake_run_lane(*a, **k):
        return None

    monkeypatch.setattr(worker.service, "run_lane", fake_run_lane)
    monkeypatch.setattr(worker, "_bucket_reader", FakeReader())
    monkeypatch.setattr(worker, "_next_bucket_read", None)
    await worker.tick(now=now, maintenance=False)
    await worker.tick(now=now + timedelta(seconds=30), maintenance=False)
    assert seen == [("example", "b1", "p/", "cdn")]
    await worker.tick(now=now + timedelta(seconds=61), maintenance=False)
    assert len(seen) == 2


async def test_tick_skips_bucket_reader_when_disabled(conn, pool, config_dir, now, monkeypatch):
    class Boom:
        async def read_new(self, *a, **k):
            raise AssertionError("must not run")

    async def fake_run_lane(*a, **k):
        return None

    monkeypatch.setattr(worker.service, "run_lane", fake_run_lane)
    monkeypatch.setattr(worker, "_bucket_reader", Boom())
    monkeypatch.setattr(worker, "_next_bucket_read", None)
    await worker.tick(now=now, maintenance=False)


async def test_tick_runs_only_the_asked_lanes(conn, pool, config_dir, now, monkeypatch):
    ran = []

    async def fake_run_lane(site_id, lane, pool=None, steps=None):
        ran.append(lane)
        return object()

    monkeypatch.setattr(worker.service, "run_lane", fake_run_lane)
    await worker.tick(now=now, maintenance=False, lanes=(Lane.SLOW,))
    assert ran == [Lane.SLOW]


async def test_slow_lane_does_not_block_fast_lane(conn, pool, config_dir, monkeypatch):
    import asyncio

    release = asyncio.Event()
    fast_runs = []

    async def fake_run_lane(site_id, lane, pool=None, steps=None):
        if lane == Lane.SLOW:
            await release.wait()  # a slow LLM call
        else:
            fast_runs.append(site_id)
        return object()

    monkeypatch.setattr(worker.service, "run_lane", fake_run_lane)
    stop = asyncio.Event()
    task = asyncio.create_task(worker.run_loops("all", tick_seconds=0.01, stop=stop))
    try:
        async with asyncio.timeout(5):
            while len(fast_runs) < 3:
                await asyncio.sleep(0.01)
        assert not release.is_set()
    finally:
        release.set()
        stop.set()
        await task


async def test_slow_lock_skip_does_not_burn_the_interval(conn, pool, config_dir, now, monkeypatch):
    async def fake_run_lane(site_id, lane, pool=None, steps=None):
        return None  # the lock is taken (for example "Generate now" is running)

    monkeypatch.setattr(worker.service, "run_lane", fake_run_lane)
    await worker.tick(now=now, maintenance=False, lanes=(Lane.SLOW,))
    cur = await conn.execute(
        "select next_due_at from site_work where site_id = 'example' and lane = 'slow'"
    )
    (due,) = await cur.fetchone()
    assert due - now <= timedelta(minutes=10)  # not the 6 h window


async def test_maintenance_prunes_derived_tables(conn, pool, config_dir, now, monkeypatch):
    calls = []

    async def fake_prune():
        calls.append("prune")
        return {}

    async def noop(*a, **k):
        return {}

    monkeypatch.setattr(worker.cleanup, "run_cleanup", noop)
    monkeypatch.setattr(worker.verify, "download_snapshots", noop)
    monkeypatch.setattr(worker.retention, "run_retention", fake_prune)
    monkeypatch.setattr(worker, "_next_maintenance", {})
    await worker._maintenance(now)
    assert calls == ["prune"]


async def test_pool_connections_use_utc(pool):
    async with pool.connection() as c:
        cur = await c.execute("show timezone")
        assert (await cur.fetchone())[0] == "UTC"
