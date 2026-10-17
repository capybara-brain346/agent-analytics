import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta

from prometheus_client import Counter, Gauge
from psycopg import AsyncConnection

from src.config import get_settings
from src.logger import get_logger
from src.models.domain import Lane, RunStatus
from src.services import (
    alerts,
    classify,
    importer,
    pairing,
    recommendations,
    reconstruction,
    verify,
)
from src.store import db, locks, runs, work

log = get_logger(__name__)

Step = Callable[[AsyncConnection, str], Awaitable[dict]]

FAST_STEPS: tuple[tuple[str, Step], ...] = (
    ("import", importer.import_due_files),
    ("pair", pairing.pair_events),
    ("verify", verify.verify_new_clients),
    ("classify", classify.classify_new_verdicts),
    ("views", reconstruction.update_views),
)

RUNS_TOTAL = Counter("pipeline_runs_total", "Pipeline runs", ["lane", "status"])
FILES_WAITING = Gauge("import_files_waiting", "Import files with status new")


class LockTaken(Exception):
    pass


class RunFailed(Exception):
    def __init__(self, run_id: str, failed_step: str | None, error: str | None):
        super().__init__(f"run {run_id} failed at {failed_step}: {error}")
        self.run_id = run_id
        self.failed_step = failed_step
        self.error = error


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    failed_step: str | None
    error: str | None
    counts: dict


def slow_interval(window: str) -> timedelta:
    # MVP: the slow lane runs once for each window (6 h window = every 6 h; 14 d = every 2 weeks).
    match = re.fullmatch(r"(\d+)([hd])", window.strip())
    if not match:
        return work.DEFAULT_SLOW_INTERVAL
    amount, unit = int(match[1]), match[2]
    return timedelta(hours=amount) if unit == "h" else timedelta(days=amount)


@asynccontextmanager
async def _connection(pool=None) -> AsyncIterator[AsyncConnection]:
    # Autocommit: every statement commits, and `conn.transaction()` opens the step transaction.
    async with (pool or db.pool()).connection() as conn:
        await conn.set_autocommit(True)
        try:
            yield conn
        finally:
            with suppress(Exception):  # a broken connection is dropped by the pool
                await conn.set_autocommit(False)


async def _execute(
    conn: AsyncConnection, site_id: str, lane: Lane, steps: Sequence[tuple[str, Step]]
) -> RunResult:
    run_id = await runs.start_run(conn, site_id, lane)
    log_extra = {"site_id": site_id, "lane": lane.value, "run_id": run_id}
    counts: dict = {}
    failed_step = error = None
    for name, step in steps:
        try:
            async with conn.transaction():
                counts[name] = await step(conn, site_id)
        except Exception as exc:
            failed_step = name
            error = f"{type(exc).__name__}: {exc}"[:2000]
            log.exception("step failed", extra=log_extra | {"step": name})
            break
    status = RunStatus.FAILED if failed_step else RunStatus.SUCCESS
    await runs.finish_run(conn, run_id, status, failed_step, error, counts)
    await work.record_run(conn, site_id, lane, success=status == RunStatus.SUCCESS)
    RUNS_TOTAL.labels(lane.value, status.value).inc()
    log.info("run finished", extra=log_extra | {"status": status.value, "counts": counts})
    try:
        await alerts.check_failed_runs(conn, site_id)
    except Exception:
        log.exception("alert check failed", extra=log_extra)
    return RunResult(run_id, status.value, failed_step, error, counts)


# Optional arguments that run_lane passes to the steps (tests and tools inject them).
_STEP_ARGS = {
    "import": ("inbox", "now"),
    "pair": ("now",),
    "verify": ("now", "resolver"),
    "views": ("now",),
}


def _with_injection(steps: Sequence[tuple[str, Step]], injected: dict) -> list[tuple[str, Step]]:
    injected = {k: v for k, v in injected.items() if v is not None}
    wrapped = []
    for name, step in steps:
        extra = {k: injected[k] for k in _STEP_ARGS.get(name, ()) if k in injected}
        if extra:

            async def call(conn, site_id, step=step, extra=extra):
                return await step(conn, site_id, **extra)

            wrapped.append((name, call))
        else:
            wrapped.append((name, step))
    return wrapped


def _slow_steps(window: str, now: datetime | None = None) -> list[tuple[str, Step]]:
    async def generate(conn: AsyncConnection, site_id: str) -> dict:
        extra = {"now": now} if now is not None else {}
        return {"run_id": await recommendations.generate(conn, site_id, window, **extra)}

    return [("recommendations", generate)]


async def run_lane(
    site_id: str,
    lane: Lane,
    pool=None,
    steps: Sequence[tuple[str, Step]] | None = None,
    now: datetime | None = None,
    inbox=None,
    resolver=None,
) -> RunResult | None:
    # None = the site + lane lock is taken: skip, do not queue (7.2).
    # now, inbox and resolver are optional injections for the steps that take them.
    lane = Lane(lane)
    if steps is None:
        if lane == Lane.FAST:
            steps = _with_injection(FAST_STEPS, {"now": now, "inbox": inbox, "resolver": resolver})
        else:
            steps = _slow_steps(get_settings().recommendation_window, now)
    async with _connection(pool) as conn, locks.site_lane_lock(conn, site_id, lane) as got:
        if not got:
            log.info("lock taken, skip", extra={"site_id": site_id, "lane": lane.value})
            return None
        return await _execute(conn, site_id, lane, steps)


async def run_recommendations(site_id: str, window: str, pool=None) -> str:
    # Returns the recommendation run id made by recommendations.generate.
    async with _connection(pool) as conn, locks.site_lane_lock(conn, site_id, Lane.SLOW) as got:
        if not got:
            raise LockTaken(site_id)
        result = await _execute(conn, site_id, Lane.SLOW, _slow_steps(window))
    if result.status != RunStatus.SUCCESS:
        raise RunFailed(result.run_id, result.failed_step, result.error)
    return result.counts["recommendations"]["run_id"]
