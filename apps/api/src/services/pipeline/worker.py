import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta

from src.config import get_settings
from src.logger import get_logger
from src.models.domain import Lane
from src.services import alerts, cleanup, verify
from src.services.importer.bucket_reader import BucketReader, targets_from_site_files
from src.services.pipeline import retention, service
from src.services.site_config import list_sites
from src.store import db, import_files, locks, runs, work
from src.store.inbox import get_inbox

log = get_logger(__name__)

MAINTENANCE_EVERY = timedelta(days=1)
MAINTENANCE_RETRY = timedelta(hours=1)

# Time of the next daily job, kept in memory: a restart runs each job once at once, which is safe.
_next_maintenance: dict[str, datetime] = {}


_bucket_reader: BucketReader | None = None
_next_bucket_read: datetime | None = None


async def _read_buckets(now: datetime) -> None:
    # CDN log buckets (decision 1.17): copy new objects into the inbox. The reader keeps a memory
    # of objects it has seen, so one instance lives as long as the worker.
    global _bucket_reader, _next_bucket_read
    settings = get_settings()
    if not settings.bucket_reader_enabled:
        return
    if _next_bucket_read is not None and now < _next_bucket_read:
        return
    _next_bucket_read = now + timedelta(seconds=settings.bucket_reader_interval_seconds)
    if _bucket_reader is None:
        _bucket_reader = BucketReader(get_inbox())
    for target in targets_from_site_files():
        try:
            async with db.connection() as conn:
                counts = await _bucket_reader.read_new(conn, target, now)
            log.info("bucket read", extra={"site_id": target.site_id, "counts": counts})
        except Exception:
            log.exception("bucket read failed", extra={"site_id": target.site_id})


async def _maintenance(now: datetime) -> None:
    jobs = {"cleanup": cleanup.run_cleanup, "retention": retention.run_retention}
    if not get_settings().offline:
        jobs = {"download_ip_lists": verify.download_snapshots} | jobs
    for name, job in jobs.items():
        if now < _next_maintenance.get(name, now):
            continue
        try:
            await job()
            _next_maintenance[name] = now + MAINTENANCE_EVERY
        except Exception:
            log.exception("maintenance job failed", extra={"job": name})
            _next_maintenance[name] = now + MAINTENANCE_RETRY


async def close_stale_runs(now: datetime | None = None) -> int:
    # A worker crash leaves a run in status 'running'. The site + lane lock is a session lock, so a
    # free lock proves that no live worker still owns the run.
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(minutes=get_settings().stale_run_minutes)
    closed = 0
    async with service._connection() as conn:
        for run in await runs.running_runs_started_before(conn, cutoff):
            lane = Lane(run["lane"])
            async with locks.site_lane_lock(conn, run["site_id"], lane) as got:
                if not got:
                    continue
                if not await runs.fail_running_run(conn, run["id"], "worker stopped"):
                    continue
                await work.record_run(conn, run["site_id"], lane, success=False)
                await alerts.check_failed_runs(conn, run["site_id"])
                closed += 1
                log.warning("stale run closed", extra={"run_id": str(run["id"])})
    return closed


async def _run_due(conn, lane: Lane, now: datetime, sites: list[str]) -> None:
    interval = service.slow_interval(get_settings().recommendation_window)
    while (site_id := await work.take_due_site(conn, lane, now, sites, interval)) is not None:
        try:
            result = await service.run_lane(site_id, lane)
        except Exception:
            log.exception("run crashed", extra={"site_id": site_id, "lane": lane.value})
            continue
        if result is None and lane == Lane.SLOW:
            await work.release_slow(conn, site_id, now)  # lock taken: do not skip a full window


ALL_LANES = (Lane.FAST, Lane.SLOW)


async def tick(
    now: datetime | None = None, maintenance: bool = True, lanes: tuple[Lane, ...] = ALL_LANES
) -> None:
    now = now or datetime.now(UTC)
    sites = list_sites()
    try:
        await close_stale_runs(now)
    except Exception:
        log.exception("stale run check failed")
    if Lane.FAST in lanes:
        await _read_buckets(now)
    async with service._connection() as conn:
        await work.ensure_site_work(conn, sites)
        for lane in lanes:
            await _run_due(conn, lane, now, sites)
        if Lane.FAST in lanes:
            service.FILES_WAITING.set(await import_files.files_waiting(conn))
            try:
                await alerts.check_no_data(conn, now)
            except Exception:
                log.exception("no-data check failed")
    if maintenance:
        await _maintenance(now)


async def _loop(
    lanes: tuple[Lane, ...], maintenance: bool, tick_seconds: float, stop: asyncio.Event
) -> None:
    while not stop.is_set():
        try:
            await tick(lanes=lanes, maintenance=maintenance)
        except Exception:
            log.exception("worker tick failed", extra={"lanes": [x.value for x in lanes]})
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), tick_seconds)


async def run_loops(
    mode: str = "all", tick_seconds: float | None = None, stop: asyncio.Event | None = None
) -> None:
    # The pool must be open. Each lane group has its own loop (task) and its own connections,
    # so a slow recommendation run (LLM calls) never delays the next fast tick.
    # Daily maintenance runs with the slow lane: it is off the fast path.
    # mode: "fast" | "slow" | "all" (both loops in one process).
    tick_seconds = get_settings().tick_seconds if tick_seconds is None else tick_seconds
    stop = stop or asyncio.Event()
    loops = {"fast": ((Lane.FAST,), False), "slow": ((Lane.SLOW,), True)}
    if mode != "all":
        loops = {mode: loops[mode]}
    await asyncio.gather(
        *(_loop(lanes, maint, tick_seconds, stop) for lanes, maint in loops.values())
    )


async def run_forever(mode: str = "all") -> None:
    settings = get_settings()
    await db.open_pool(settings)
    log.info("worker started", extra={"tick_seconds": settings.tick_seconds, "lanes": mode})
    try:
        await run_loops(mode)
    finally:
        await db.close_pool()
