# Pipeline

The pipeline module runs the processing steps for one site and one lane. It also owns the worker loop, the locks, the work queue, the run records, daily maintenance, alerts and health.
Input: files in `import_files` with status `new`, and the site list from `apps/api/config/`. Output: rows in `pipeline_runs`, `site_work` and `alerts`, plus the data written by the steps.

## Read this when

- You change how a run starts, stops, fails or retries.
- You add, remove or reorder a step in `FAST_STEPS`.
- You change the worker loop, the tick, or the lane modes (`fast`, `slow`, `all`).
- You change a lock (site + lane lock, step transaction, view transaction).
- You change which site a worker takes next (fair turns, work limit, slow interval).
- You change daily maintenance (cleanup, retention, IP list download).
- You change an alert (`no_data`, `failed_runs`), `/health`, `/livez` or the freshness banner.
- You change `run-pipeline`, `run-recommendations` or `worker` CLI commands.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/services/pipeline/service.py` | `run_lane`, `run_recommendations`, `FAST_STEPS`, step transaction, run records, Prometheus metrics. |
| `apps/api/src/services/pipeline/worker.py` | `tick`, `run_loops`, `run_forever`, stale-run close, bucket-read call, daily maintenance schedule. |
| `apps/api/src/services/pipeline/retention.py` | `run_retention`, `prune_derived`: delete old derived rows. |
| `apps/api/src/services/pipeline/__init__.py` | Public exports of the module. |
| `apps/api/src/services/cleanup/service.py` | `run_cleanup`: delete old inbox objects, drop old `events_YYYYMMDD` partitions, create next partitions, prune bucket marks. |
| `apps/api/src/services/alerts/service.py` | `check_no_data`, `check_failed_runs`. |
| `apps/api/src/store/locks.py` | Advisory locks: `site_lane_lock`, `try_site_lane_xact_lock`, `advisory_lock`, `lock_key`, `bucket_lock_key`. |
| `apps/api/src/store/work.py` | `site_work` table access: `ensure_site_work`, `take_due_site`, `record_run`, `release_slow`. |
| `apps/api/src/store/runs.py` | `pipeline_runs` table access. |
| `apps/api/src/store/retention.py` | `prune_older_than`: delete statements for derived tables. |
| `apps/api/src/store/alerts.py` | `alerts` table access: `raise_alert`, `resolve_alert`, `list_alerts`. |
| `apps/api/src/store/queries.py` | `freshness`, `open_alerts`, `latest_run`, `list_pipeline_runs`, `get_pipeline_run` (read side for the dashboard). |
| `apps/api/src/routes/health.py` | `GET /livez`, `GET /health`. |
| `apps/api/src/routes/runs.py` | `GET /api/runs`, `GET /api/runs/{run_id}`. |
| `apps/api/src/routes/overview.py` | `banner`: the freshness banner text and state. |
| `apps/api/src/routes/metrics.py` | `GET /metrics` (Prometheus). |
| `apps/api/src/cli.py` | `worker`, `run-pipeline`, `run-recommendations`, `cleanup` commands. |
| `apps/api/src/models/domain.py` | Enums `Lane`, `RunStatus`, `AlertKind`. |
| `apps/api/migrations/versions/0001_initial.py` | Tables `pipeline_runs`, `site_work`, `alerts`, index `alerts_open`. |
| `apps/api/tests/pipeline/` | All tests of this module. |

Module READMEs next to the code: `apps/api/src/services/pipeline/README.md`, `apps/api/src/services/cleanup/README.md`, `apps/api/src/services/alerts/README.md`.

## Data flow

Two lanes. Each lane runs for one site at a time.

```
 FAST LANE  (every tick, 60 s)                         SLOW LANE (once for each window)
 ─────────────────────────────                         ────────────────────────────────
 import ─► pair ─► verify ─► classify ─► views          recommendations
 (FAST_STEPS, in this order)                           (window = RECOMMENDATION_WINDOW)

 user sees: events, verdicts, classes, sessions,       user sees: recommendation list
 agents, pages, journeys, counts, trends, import       MVP default: every 6 h, 6 h window
 status, alerts                                        Production: every 2 weeks, 14 d window
                                                       Also: "Generate now" button / CLI
```

Worker and work line. The `import_files` table is the queue. There is no queue product.

```
 worker 1..N (same image)
   loop (each tick):
     close_stale_runs
     read CDN buckets (fast loop only)
     ensure_site_work  (a site_work row for each site + lane)
     for each lane of this loop:
       take_due_site ──► site_id  (UPDATE ... FOR UPDATE SKIP LOCKED LIMIT 1)
       run_lane(site_id, lane)
         site + lane advisory lock taken? ── no ──► skip (do not queue)
         run the steps for this site only
       repeat until take_due_site returns None
     set import_files_waiting gauge, check_no_data  (fast loop only)
     daily maintenance                              (slow loop only)

 site A ── lock A ── worker 1 ┐
 site B ── lock B ── worker 2 ├─ in parallel; one site + lane never runs twice at once
 site C ── lock C ── worker 3 ┘
```

One run (one site, one lane):

```
 worker loop  or  CLI / button
        │
        ▼
 run_lane(site_id, lane)
        │
        ▼
 take site + lane lock ── taken by another? ──► return None (skip)
        │
        ▼
 start_run  ──► pipeline_runs row, status = running
        │
        ▼
 step 1 ─► step 2 ─► ... ─► step N       each step = one transaction
        │
        ├─ all OK ───► status = success   · site_work.last_success_at = now
        └─ step K fails ─► stop; later steps do not run
                           status = failed (failed_step, error)
                           steps before K keep their writes
        │
        ▼
 record_run (site_work) ─► check_failed_runs (alert) ─► release lock
```

Sequence: one worker tick for one site.

```
 worker        store.work        store.locks       pipeline_runs     step
   │ take_due_site  │                  │                  │            │
   │───────────────►│ claim row        │                  │            │
   │◄───site_id─────│                  │                  │            │
   │ pg_try_advisory_lock              │                  │            │
   │──────────────────────────────────►│                  │            │
   │◄─────────────────got──────────────│                  │            │
   │ start_run ───────────────────────────────────────────►│            │
   │ BEGIN; step(conn, site_id) ───────────────────────────────────────►│
   │◄──────────────────────────────────────counts / error───────────────│
   │ finish_run ──────────────────────────────────────────►│            │
   │ record_run ───►│                  │                  │            │
   │ unlock ───────────────────────────►│                  │            │
```

View update (the `views` step) runs in one transaction:

```
 BEGIN
   upsert open_sessions, current-hour rows        (one site only)
   move closed visits ─► sessions (append)
 COMMIT ──► dashboard sees the new rows
   └─ fail ──► ROLLBACK; old rows stay; dashboard shows old data
```

## Rules and decisions

Real-time context:

- Real-time scope: the product needs near real-time, not real time. The floor is the customer log delivery (CDN push batch, Vector flush). Expect about 1 to 6 minutes after the request. Why: real time is not a requirement. The requirements are: file import misses real-time data, so ingest asynchronously and alert when data stops arriving.
- [7.7] A session with a last event less than 30 minutes ago is "in progress". An older session is "closed". Why: honest label: a later import can change an open session. The 30 minutes come from `session_gap_minutes`. `in_progress` is set in `apps/api/src/store/queries.py` by the union of `sessions` and `open_sessions`.

Run rules:

- [7.1] Two lanes. `run-pipeline fast` runs the five `FAST_STEPS` (import, pair, verify, classify, views). `run-pipeline slow` runs recommendations. Each command runs for one site. The trigger is a loop inside the worker process. The CLI stays for manual runs. Why: the back end owns the logic. A loop needs no extra service and has no container start delay at a 1-minute tick.
- [7.2] One lock for each site + lane (L1). Lock taken means skip that site this tick. Do not queue. Why: Postgres allows many writers. A global lock would make all sites wait for the largest one.
- [7.3] A failed step stops the run. Earlier steps keep their writes. Why: later steps need complete input.
- [7.4] Each step is one transaction. A step processes "not done yet" work only. The next tick is the retry. There is no special retry code. Why: a failed run is safe to repeat.
- [7.5] View rows of one site are updated in one transaction (L3, decision 4.7 in `../activity-reconstruction/README.md`). Why: the dashboard never shows half-built data, and reads never wait.
- Steps run in order, one after another. Each step needs the output of the step before. Steps import, pair, verify and classify process new work only. The views step updates open sessions and the current hour.
- Backfill (old logs from upload or CLI, decision 1.18 in `../ingestion/README.md`) uses the fast-lane steps at low priority. `import_files.claim_next_file` takes live files first, then backfill, oldest first.
- A run records `counts` for each step as JSON in `pipeline_runs.counts`. A step returns a `dict`.
- A step failure stores `"{ExceptionType}: {message}"` cut to 2000 characters in `pipeline_runs.error`.
- After each run, `check_failed_runs` runs. An error in the alert check does not fail the run.

Alerts and health:

- [7.6] Raise an alert after 3 failed runs in a row (`FAILED_RUNS_ALERT`). `/health` returns the last success of each lane. A lane is unhealthy when its last success is older than the limit. Why: operators need health checks and error logging. Phase 2 infrastructure uses `/health`.
- [7.11] `/health` and the stale rule apply for each site and lane. Why: many sites in one system.
- A `no_data` alert is raised for a source when no new live file arrived within `no_data_alert_minutes` (site file value, or the `NO_DATA_ALERT_MINUTES` default). Only live files count. A backfill upload must not hide a sender that stopped (decisions 1.4, 1.18). A source that never sent a file has no baseline and raises no alert. The alert resolves when a new live file arrives.
- An alert is unique for each open (`site_id`, `kind`, `source`) by the index `alerts_open`. `raise_alert` returns `None` when the same alert is open. `resolve_alert` sets `resolved_at`.
- A `failed_runs` alert has no source. It covers both lanes of a site. It resolves when no lane has the threshold of failures.

Queue, workers and scaling:

- [7.8] No queue product (SQS, Kafka). `import_files` plus `FOR UPDATE SKIP LOCKED` is the queue. Add one only on a measured need: job polling loads the database, a seconds-level delay is required, or other systems must react to new files. Why: a second list of work must be kept in agreement with the table. Load is about 7 requests/s. Postgres handles thousands.
- [7.9] N workers, same image. Fair turns: the site that waited longest goes first (`order by last_run_at nulls first, site_id`). Work limit for each run: 200 MB or 2 M lines (`WORK_LIMIT_BYTES`, `WORK_LIMIT_LINES`). The rest waits for the next turn. Why: one large site cannot block the others.
- [7.10] Cap workers to fit the database connection limit (`DB_POOL_MAX_SIZE` for each process). Why: upload is not the bottleneck. Processing is, and in processing the database is the shared limit. More workers help parsing. Decision 4.1 (see `../store/README.md`) keeps database work small.
- The `import_files` table is the queue. The file is in the inbox, its row says "not done", a crash leaves it "not done", and the count of waiting rows drives scaling (gauge `import_files_waiting`).
- The fast lane is due for every configured site once each tick. An idle run is a few empty queries. The slow lane is due when `site_work.next_due_at` has passed.
- A worker process runs one loop for each lane group. A slow run (LLM calls) does not delay the next fast tick.
- A lock-taken skip on the slow lane sets `next_due_at` to now + 5 minutes (`LOCK_SKIP_RETRY`). It does not wait a full window.
- A failed slow run sets `next_due_at` to now + 15 minutes (`SLOW_RETRY_AFTER`).

Locks:

| # | Lock | Scope | Purpose |
|---|---|---|---|
| L1 | Site lock (Postgres session advisory lock, `site_lane_lock`) | One site + lane | Sites run in parallel. One site never runs twice at once. |
| L2 | Step transaction (`conn.transaction()` in `_execute`) | One step | No half-written step. The next tick is the retry. |
| L3 | View-row transaction (decision 4.7) | One site's view rows | Readers see old or new rows, never a mix. |
| L4 | Unique `import_files.sha256` (decision S.6) | One file | Two copies of one chunk cannot both import. |

- The L1 key is `sha256("{site_id}:{lane}")`, first 8 bytes, signed. `try_site_lane_xact_lock` uses the same key. `importer.delete_import` takes it as a transaction lock with `Lane.FAST`, so a delete and a fast run exclude each other.
- The run connection uses autocommit. Each statement commits. `conn.transaction()` opens the step transaction. The session lock survives these commits.
- The bucket reader uses its own lock key (`bucket_lock_key`) with `advisory_lock`.

"Not done yet" (why a failed run is safe to repeat):

| Step | "Not done yet" means |
|---|---|
| Import | File status is not `success`. |
| Pair | Event not paired, wait window not over. |
| Verify | Client key with no current verdict. |
| Classify | Verdict row with no class. |
| Views | Open sessions and current hour of a site with new events. |

Failure and not a failure:

| NOT a failure (handled inside the step) | A failure (stops the run) |
|---|---|
| Bad line: goes to rejects. | Database error. |
| Bad file: file marked failed, other files continue. | Bug or exception in code. |
| DNS timeout: verdict `UNVERIFIED`. | Disk full. |
| LLM error: template text. | |

Stale runs:

- A worker crash leaves a run in status `running`. `close_stale_runs` runs at the start of each tick. It closes a run that is older than `STALE_RUN_MINUTES` when the site + lane lock is free. A free lock proves that no live worker owns the run. The run becomes `failed` with error `worker stopped`. `site_work` counts it as a failure.

Maintenance (daily):

- Daily jobs run in the slow loop only, off the fast path. Jobs: `download_ip_lists` (skipped when `OFFLINE` is true), `cleanup`, `retention`.
- The next time of each job is kept in memory (`_next_maintenance`). A restart runs each job once at once. This is safe.
- A failed job retries after 1 hour (`MAINTENANCE_RETRY`). A good job runs again after 1 day (`MAINTENANCE_EVERY`).
- `run_cleanup` does: delete inbox objects of imported files older than `RAW_RETENTION_DAYS` (sets `import_files.object_deleted_at`, the row stays so sha256 still blocks a second copy, S.6); drop `events_YYYYMMDD` partitions older than `EVENTS_RETENTION_DAYS` (detach concurrently, then drop); prune `bucket_objects` marks older than `RAW_RETENTION_DAYS`; create partitions for today and the next 3 days (`PARTITION_DAYS_AHEAD`). A failed object delete keeps the file marked as present. The next daily run tries again.
- `run_retention` deletes derived rows older than `EVENTS_RETENTION_DAYS`. Why: derived rows live as long as the raw events they come from. Tables: `page_stats`, `journey_steps`, `agents`, `session_events`, `sessions`, `pipeline_runs` (not `running`), `import_rejects` (of old files).

Bucket reader call:

- In the fast loop, the tick calls the CDN bucket reader (decision 1.17, `../ingestion/README.md`) when `BUCKET_READER_ENABLED` is true and `BUCKET_READER_INTERVAL_SECONDS` has passed. One reader instance lives as long as the worker. An error for one site is logged and does not stop the tick.

Why not swap tables for the view update:

- One table holds many sites, so a swap rebuilds every site.
- The rename needs an exclusive lock that waits behind slow dashboard reads and blocks all new reads.
- Indexes, grants and Postgres views attached to the old table are lost.

Freshness banner (what the user sees):

- `pipeline_runs` shows: `id`, `lane`, `started_at`, `finished_at`, `status`, `failed_step`, `error`, `counts`.
- The banner `state` comes from `routes/overview.py: banner`, in this order of priority:

| Condition | `state` | Text |
|---|---|---|
| Open `failed_runs` alert | `alert_failing` | `ALERT: pipeline failing since HH:MM` |
| Open `no_data` alert | `alert_no_data` | `ALERT: no new logs from <site> since HH:MM` |
| Latest fast run is `running` | `updating` | `Updating... (data up to HH:MM)` |
| Latest fast run is `failed` | `last_run_failed` | `Data up to HH:MM - last run failed at <step>` |
| No run and no `data_up_to` | `no_runs` | `No pipeline run yet` |
| Otherwise | `ok` | `Data up to HH:MM` |

- `data_up_to` is the newest `finished_at` of a successful fast run (`queries.freshness`). It falls back to `site_work.last_success_at`.

## Configuration

Names are fields of `Settings` in `apps/api/src/config/settings.py`. The env var name is the field name in upper case, with no prefix. A value can also come from `apps/api/.env`.

| Setting | Default | Effect |
|---|---|---|
| `tick_seconds` | `60` | Seconds between worker ticks. |
| `work_limit_bytes` | `200 MiB` | Import step stops taking new files after this many bytes in one run. |
| `work_limit_lines` | `2_000_000` | Import step stops after this many lines in one run. |
| `health_stale_minutes` | `15` | Fast lane: `/health` is unhealthy when the last success is older. Slow lane: this margin is added to the window. |
| `stale_run_minutes` | `30` | A `running` run older than this, with a free lock, is closed as failed. |
| `failed_runs_alert` | `3` | Failed runs in a row that raise a `failed_runs` alert. |
| `recommendation_window` | `"6h"` | Window of the slow lane. Also sets the slow interval (`6h` = every 6 h, `14d` = every 14 days). |
| `raw_retention_days` | `7` | Cleanup deletes inbox objects and bucket marks older than this. |
| `events_retention_days` | `30` | Cleanup drops event partitions older than this. Retention deletes derived rows older than this. |
| `no_data_alert_minutes` | `60` | Default time limit for the `no_data` alert. A site file key `no_data_alert_minutes` overrides it. |
| `bucket_reader_enabled` | `False` | Turns on the CDN bucket read in the fast loop. |
| `bucket_reader_interval_seconds` | `60` | Time between bucket reads. |
| `offline` | `False` | Skips the daily `download_ip_lists` job. |
| `db_pool_max_size` | `10` | Pool size for each process (decision 7.10). |

Constants in code:

| Name | Value | Where |
|---|---|---|
| `MAINTENANCE_EVERY` | 1 day | `services/pipeline/worker.py` |
| `MAINTENANCE_RETRY` | 1 hour | `services/pipeline/worker.py` |
| `DEFAULT_SLOW_INTERVAL` | 6 hours (used when the window text is not `<n>h` or `<n>d`) | `store/work.py` |
| `SLOW_RETRY_AFTER` | 15 minutes | `store/work.py` |
| `LOCK_SKIP_RETRY` | 5 minutes | `store/work.py` |
| `PARTITION_DAYS_AHEAD` | 3 | `services/cleanup/service.py` |

## Interfaces

Python (`from src.services import pipeline`):

| Name | Signature / meaning |
|---|---|
| `run_lane` | `async run_lane(site_id, lane, pool=None, steps=None, now=None, inbox=None, resolver=None) -> RunResult \| None`. `None` = lock taken. `now`, `inbox`, `resolver` are test injections for the steps that take them. |
| `run_recommendations` | `async run_recommendations(site_id, window, pool=None) -> str`. Returns the recommendation run id. Raises `LockTaken` or `RunFailed`. |
| `FAST_STEPS` | `tuple[tuple[str, Step], ...]`: `import`, `pair`, `verify`, `classify`, `views`. `Step = Callable[[AsyncConnection, str], Awaitable[dict]]`. |
| `RunResult` | Frozen dataclass: `run_id`, `status`, `failed_step`, `error`, `counts`. |
| `LockTaken`, `RunFailed` | Exceptions. `RunFailed` has `run_id`, `failed_step`, `error`. |
| `slow_interval` | `slow_interval(window: str) -> timedelta`. |
| `tick` | `async tick(now=None, maintenance=True, lanes=(Lane.FAST, Lane.SLOW))`. |
| `run_loops` | `async run_loops(mode="all", tick_seconds=None, stop=None)`. The pool must be open. |
| `run_forever` | `async run_forever(mode="all")`. Opens and closes the pool. |

Other:

- `services.cleanup.run_cleanup(conn=None, inbox=None, now=None) -> dict` returns `{"files_deleted", "partitions_dropped"}`.
- `services.pipeline.retention.run_retention() -> dict[str, int]` returns deleted rows for each table.
- `services.alerts.check_no_data(conn, now)` and `check_failed_runs(conn, site_id)`.
- `store.locks.site_lane_lock(conn, site_id, lane)` is an async context manager that yields `bool`.
- `store.work`: `ensure_site_work(conn, site_ids)`, `take_due_site(conn, lane, now, site_ids=None, slow_interval=...)`, `record_run(conn, site_id, lane, success)`, `release_slow(conn, site_id, now)`.
- `store.runs`: `start_run`, `finish_run`, `running_runs_started_before`, `fail_running_run`, `last_success_by_lane`, `consecutive_failures`, `recent_runs`.

CLI (from `apps/api`; the full CLI list is in `../api/README.md`):

| Command | Behavior |
|---|---|
| `uv run python -m src.cli worker [--lanes fast\|slow\|all]` | Run the worker loop. Default `all`: two loops in one process. |
| `uv run python -m src.cli run-pipeline <fast\|slow> --site <id>` | One run now. Exit 0 = success. Exit 1 = run failed. Exit 2 = lock taken (skipped). The slow lane uses `RECOMMENDATION_WINDOW`. |
| `uv run python -m src.cli run-recommendations --site <id> [--window 6h\|14d]` | Slow-lane run with a chosen window. Exit 1 on lock taken or failure. |
| `uv run python -m src.cli cleanup` | Run `run_cleanup` now. |

HTTP:

| Endpoint | Meaning |
|---|---|
| `GET /livez` | `{"status": "ok"}`. Process is alive. |
| `GET /health` | `HealthReport`: `healthy`, `lanes[]` (`site_id`, `lane`, `last_success`, `healthy`), open `alerts[]`. Status 503 when any lane is unhealthy or the database check fails. Open alerts do not change `healthy`. Open (no auth). |
| `GET /metrics` | Prometheus. Pipeline metrics: counter `pipeline_runs_total{lane,status}`, gauge `import_files_waiting`. Open (no auth). |
| `GET /api/runs`, `GET /api/runs/{run_id}` | Pipeline runs of a site (`lane`, `status` filters). Needs the API token. |
| `POST /api/recommendations/generate` | "Generate now": calls `run_recommendations`. 409 `lock_taken`, 500 `run_failed`. Details in `../recommendations/README.md`. |

Tables: `pipeline_runs` (`id`, `site_id`, `lane`, `started_at`, `finished_at`, `status`, `failed_step`, `error`, `counts`), `site_work` (`site_id`, `lane`, `last_run_at`, `last_success_at`, `consecutive_failures`, `next_due_at`), `alerts` (`id`, `site_id`, `kind`, `source`, `message`, `raised_at`, `resolved_at`).

## Known limits

- The in-memory schedule of daily jobs and the bucket reader state are lost at restart. A restart runs each daily job once. This is safe.
- A worker runs the due sites of its lane one after another. Parallelism comes from more workers, not from threads in one worker.
- The work limit is checked before the import step claims the next file. One run can pass the byte limit by the size of one file.
- No queue product. If job polling loads the database, a seconds-level delay is required, or other systems must react to new files, review decision 7.8.
- A lock-taken skip on the fast lane drops that tick for that site. The next tick runs it.
- The no-data alert and the no-data banner depend on live files only. A site that only uploads backfill files has no baseline.
- The trigger (cron or timer outside the worker) is phase 2 infrastructure. The back end has commands and the worker loop only.

## Open questions

None for this module.

## How to change

| Change | Steps |
|---|---|
| Add a fast-lane step | Write the step as `async def step(conn, site_id) -> dict` in its service. Add `("name", fn)` to `FAST_STEPS` in `services/pipeline/service.py`. If it takes `now`, `inbox` or `resolver`, add it to `_STEP_ARGS`. Make it process "not done yet" work only. Update the "Not done yet" table here. Add a case to `tests/pipeline/test_run_lane.py`. |
| Change the tick or the slow window | Change `tick_seconds` or `recommendation_window` in `config/settings.py`. Update the table above. |
| Add a daily job | Add it to the `jobs` dict in `_maintenance` in `services/pipeline/worker.py`. Test in `tests/pipeline/test_worker.py` (`test_tick_runs_maintenance_daily`). |
| Prune a new derived table | Add `table: condition` to `_PRUNE` in `store/retention.py`. Extend `tests/pipeline/test_retention.py`. |
| Add an alert kind | Add the value to `AlertKind` in `models/domain.py` and to the `kind` check in a new migration. Add a `check_*` function in `services/alerts/service.py`. Call it from `_execute` or `tick`. Add the case to `banner` in `routes/overview.py`. Test in `tests/pipeline/test_alerts.py`. |
| Change the lock key or scope | Edit `store/locks.py`. Check `importer.delete_import`, which uses the same key with `try_site_lane_xact_lock`. Update `tests/pipeline/test_store.py`. |
| Change the health rule | Edit `stale_after` in `routes/health.py`. Update `tests/pipeline/test_health.py`. |

## Tests

Folder: `apps/api/tests/pipeline/`. Tests need Postgres on port 55432 (see `apps/api/README.md`).

| File | Covers |
|---|---|
| `test_run_lane.py` | Run success, failed step stops the run, lock skip, 3-failure alert, slow lane, `run_recommendations`, `slow_interval`. |
| `test_worker.py` | Tick, maintenance, bucket reader schedule, lane modes, slow lane does not block fast lane, slow lock skip. |
| `test_store.py` | Lock exclusion, run records, fair turns, `SKIP LOCKED`, slow due time, alert idempotence. |
| `test_stale_runs.py` | Crashed run closed, live-lock run left alone. |
| `test_health.py` | `/health` ok, stale 503, never ran, `/livez`. |
| `test_alerts.py` | `no_data` alert names source and resolves; backfill does not count; never-sent source. |
| `test_retention.py` | Derived rows pruned by age only. |
| `test_cli.py` | CLI wiring and exit codes (also covers `import`, `cleanup`, `worker`). |

Command, from `apps/api`: `uv run pytest tests/pipeline`.

## Related modules

- [ingestion](../ingestion/README.md): the import step, `import_files`, bucket reader, backfill priority.
- [pairing](../pairing/README.md), [verification](../verification/README.md), [classification](../classification/README.md): fast-lane steps.
- [activity-reconstruction](../activity-reconstruction/README.md): the `views` step and decision 4.7.
- [recommendations](../recommendations/README.md): the slow lane step and "Generate now".
- [store](../store/README.md): database, partitions, decision 4.1.
- [api](../api/README.md): full CLI list, routes, auth.
- [dashboard](../dashboard/README.md): freshness banner and run screens.
- [deployment](../deployment/README.md): worker scaling and phase 2 trigger.
- [architecture](../architecture/README.md): system overview.
