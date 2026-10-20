# Store

The store is the one PostgreSQL database and the S3 inbox. It is the only code that runs SQL or calls S3.
Input: function calls from routes and services with an open connection. Output: rows, counts and raw-file lines.

## Read this when

- You add or change a table, column, index or migration.
- You write SQL. All SQL goes in `apps/api/src/store/`.
- You change how raw files are saved, read, gunzipped or deleted in the S3 inbox.
- You change the `events` partitions or retention.
- You change how a service gets a database connection or a lock.
- You ask if a new database is needed for more log volume.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/store/README.md` | Short file index of the store code. |
| `apps/api/src/store/db.py` | Async connection pool: `open_pool`, `close_pool`, `pool`, `connection`. |
| `apps/api/src/store/inbox.py` | S3 inbox: `Inbox` interface, `S3Inbox`, `get_inbox`, gunzip, line splitter. |
| `apps/api/src/store/import_files.py` | `import_files` state machine, `import_rejects`, `bucket_objects`. |
| `apps/api/src/store/events.py` | `COPY` into `events`, partition create, partition drop, delete by file. |
| `apps/api/src/store/pairing.py` | Pair and expire SQL for pending `events`. |
| `apps/api/src/store/verdicts.py` | `verdicts` rows (append, current) and the events-to-verdict link. |
| `apps/api/src/store/classify.py` | Class columns of `verdicts`. |
| `apps/api/src/store/ip_lists.py` | `ip_list_snapshots`. |
| `apps/api/src/store/views.py` | Sessions, `session_events`, hourly rollups, `reset_site`, `mark_in_views`. |
| `apps/api/src/store/recommendations.py` | Pattern queries, `recommendation_runs`, `recommendations`, `llm_text_cache`. |
| `apps/api/src/store/runs.py` | `pipeline_runs`. |
| `apps/api/src/store/work.py` | `site_work`: fair turns, due-site claim. |
| `apps/api/src/store/locks.py` | Postgres advisory locks. |
| `apps/api/src/store/alerts.py` | `alerts`. |
| `apps/api/src/store/quota.py` | Byte quota read for `/ingest`. |
| `apps/api/src/store/retention.py` | Prune of derived tables. |
| `apps/api/src/store/queries.py` | Read queries for the dashboard routes (`Filters`, list and detail queries). |
| `apps/api/src/models/domain.py` | Enums that match the `check` constraints (`Lane`, `FileStatus`, `Verdict`, `AlertKind` and others). |
| `apps/api/src/config/settings.py` | `database_url`, `db_pool_max_size`, `s3_*`, retention days. |
| `apps/api/alembic.ini` | Alembic config. `script_location` = `migrations`. |
| `apps/api/migrations/env.py` | Alembic runner. Takes the URL from settings. |
| `apps/api/migrations/script.py.mako` | Template for a new migration. |
| `apps/api/migrations/versions/0001_initial.py` | All tables, indexes and partition functions. |
| `apps/api/migrations/versions/0002_integration.py` | `events.in_views`, `origin_line_key`, `origin_file_id`; `recommendations.score` to `numeric(8,1)`. |
| `apps/api/migrations/versions/0003_import_fixes.py` | `events.imported_at`, `import_files.lines_done`, `import_files.retries`, table `bucket_objects`. |
| `apps/api/migrations/versions/0004_view_fixes.py` | `retry_paths` and `last_seen` index on `sessions` and `open_sessions`. |
| `apps/api/migrations/versions/0005_import_fixes2.py` | New `ensure_events_partition` (ATTACH). Removes `drop_events_partitions_older_than`. |
| `apps/api/tests/foundation/test_infra.py` | Schema, partition function, dedupe index, fixtures, `MemoryInbox`. |
| `apps/api/tests/foundation/test_import_files_store.py` | `import_files` store functions. |
| `apps/api/tests/conftest.py` | Test database: fresh DB, `alembic upgrade head`, truncate before each test. |
| `apps/api/tests/fakes.py` | `MemoryInbox` (in-memory `Inbox`). |

The table list with columns, indexes, writers and readers is in [schema.md](schema.md).

## Data flow

```
 routes / services                      src/store                         external
 -----------------                      ---------                         --------
 route /ingest  --(bytes)-------------> inbox.put_stream ---(objects)---> S3 inbox
 importer       --(object_key)--------> inbox.open_lines <--(lines)------ S3 inbox
 cleanup        --(object_key)--------> inbox.delete -------(delete)----> S3 inbox

 importer       --(row tuples)--------> events.copy_events -+
 pairing        --(site, window)------> pairing.*           |
 verify/classify--(verdict rows)-------> verdicts.*, classify.*, ip_lists.*
 reconstruction --(site, params)-------> views.*             +--(SQL)----> PostgreSQL
 recommendations--(site, window)-------> recommendations.*   |             (one database)
 pipeline       --(run, lane)---------> runs.*, work.*, locks.*
 alerts, cleanup--(site, cutoff)-------> alerts.*, retention.*, events.drop_old_partitions
 API routes     --(Filters)-----------> queries.* ----------+
                                                              rows (dict) go back to the caller
```

Import write path inside one transaction:

```
 importer          store.import_files     store.events            PostgreSQL
    |  claim_next_file  |                      |                       |
    |------------------>|-- update ... skip locked ------------------->|
    |<--file row--------|                      |                       |
    |  copy_events(rows)                       |                       |
    |----------------------------------------->| ensure_partitions     |
    |                                          |-- own autocommit conn: select ensure_events_partition(day)
    |                                          |-- COPY into temp events_stage
    |                                          |-- insert into events ... on conflict do nothing
    |<--rows inserted--------------------------|                       |
    |  mark_success / save_progress            |                       |
    |------------------>|-- update import_files ---------------------->|
    |  commit (db.connection exits)            |                       |
```

## Rules and decisions

Decisions S.1 to S.6 come from the design. Rules ST.1 to ST.7 describe the code.

| ID | Rule | Why |
|---|---|---|
| S.1 | Use one PostgreSQL for all tables. No separate log database in the MVP. | The pipeline run needs transactions across `events`, `verdicts` and `import_files`. Two databases give no atomic write and need extra reconciliation code. One fewer service inside a bank network. |
| S.2 | `events` is partitioned by day (`RANGE` on `ts`). BRIN index on `ts`. B-tree on the client key (`events_client` on `(site_id, client_key, ts)`). Retention = remove an old partition. | Retention is cheap. No large `DELETE` and no vacuum. |
| S.3 | All reads and writes of `events` and the views go through the store module. No SQL outside `apps/api/src/store/`. | A move to another store later changes one module. |
| S.4 | Workers write view rows in an append shape: "newest version of row X" (`session_id`, `version`, values). | The same worker code works with an append-only store at scale. |
| S.5 | Scale path, only on a measured trigger: (1) bigger Postgres instance; (2) TimescaleDB compression on the same Postgres; (3) above about 1 B events/day: ClickHouse for `events` and the views (`ReplacingMergeTree` keeps the newest version). Postgres keeps metadata, verdicts and runs. | Stay on Postgres while it is cheap and simple. S.3 and S.4 make the move one module. |
| S.6 | `import_files` has a unique constraint on the file hash: `unique (site_id, sha256)`. The second insert returns no id (`insert_new` returns `None`). | Two copies of one chunk (sender retry) can arrive at the same moment. The second insert fails and the caller replies "already have it". |
| ST.1 | `ensure_events_partition` makes the table with `LIKE`, adds a range `check`, and then runs `ATTACH PARTITION`. It does not use `CREATE TABLE ... PARTITION OF`. | `PARTITION OF` takes `ACCESS EXCLUSIVE` on `events` and waits for every open import step. `ATTACH` takes only `SHARE UPDATE EXCLUSIVE`. The range `check` lets the attach skip the scan. |
| ST.2 | `events.ensure_partitions` calls the function on its own autocommit connection with `lock_timeout` set. | The partition is visible at once. The import transaction holds no lock for it. |
| ST.3 | `events.drop_old_partitions` runs `DETACH PARTITION ... CONCURRENTLY` (or `FINALIZE` for a pending detach) and then `DROP TABLE`, on its own autocommit connection. A lock timeout or a cancel leaves the partition for the next run. | A plain `DROP` of an attached partition takes `ACCESS EXCLUSIVE` on `events`. `DETACH ... CONCURRENTLY` cannot run in a transaction or in a function. |
| ST.4 | `db.connection()` is one transaction. It commits on a normal exit and rolls back on an exception. The pool opens connections with `TimeZone=UTC`. | `date_trunc` and casts must not depend on the server time zone. |
| ST.5 | `events.copy_events` loads rows by `COPY` into a temp table `events_stage`. Then one `insert ... select ... on conflict (site_id, source, line_key, ts) do nothing` fills `events`. It skips origin lines already counted in a paired row (by `origin_line_key`) and CDN lines already counted in a paired row (by `line_key`). It returns the number of inserted rows. | `COPY` is fast. A direct `COPY` into `events` cannot skip duplicates. A re-import must not insert merged lines again. |
| ST.6 | A store function takes an open `AsyncConnection` as the first argument. The caller owns the transaction. Exceptions: `events.ensure_partitions`, `events.drop_old_partitions` (own autocommit connection). | One run can combine many store calls in one transaction. |
| ST.7 | `inbox.S3Inbox.open_lines` keeps memory bounded: gunzip output comes in pieces of `DECOMPRESS_CHUNK`, a line longer than `MAX_LINE_CHARS` is cut to `MAX_LINE_CHARS + 1` characters (the adapter rejects it), and output above `max_decompressed_bytes` raises `ObjectTooLarge`. Gzip is found by the magic bytes `1f 8b`. Files of several gzip members are read. | A bad file must not use all memory. |
| ST.8 | Migrations are raw SQL in Alembic (`op.execute`). No ORM, no autogenerate. | The schema uses partitions, partial indexes and PL/pgSQL. SQL is the source of truth. |
| ST.9 | `import_files` keeps its row after the raw object is deleted (`object_deleted_at` is set). | The hash must keep blocking a second copy (S.6). |
| ST.10 | The `check` constraints in the migrations and the enums in `src/models/domain.py` must list the same values. | The store writes `Enum.value`. A new value in one place only fails at insert time. |

Current code of S.4:

- `sessions` and `open_sessions` rows carry `version`. A rebuild deletes the rows of the dirty clients and inserts them again in the same transaction. The new `version` is the old maximum plus 1.
- Hourly rows (`page_stats`, `journey_steps`, `agents`) are deleted and inserted again for the changed hours. They are never incremented.
- `close_idle_sessions` moves rows from `open_sessions` to `sessions` with `on conflict do nothing`.
- `llm_text_cache` uses `on conflict (bundle_hash) do update`.

Size check for the S.1 decision (large site, 10 M log lines/day):

| Load | Size | Postgres is enough? |
|---|---|---|
| Event writes | About 115 rows/s average, 1 to 2 k rows/s peak. | Yes. `COPY` does more than 100 k rows/s. |
| Storage | About 400 B for each row plus indexes, so 5 to 6 GB/day. | Yes, with daily partitions. |
| View updates | Only open sessions and the current hour (activity reconstruction). | Yes. Updates per minute are at most events per minute. |

Question: "Do the high log volumes need a second database?" Answer: No. Upload and write speed are not the limit. The limit is how much data each run reads again (activity reconstruction). A second database does not fix that.

## Configuration

Settings are in `apps/api/src/config/settings.py` (environment variables are the upper-case names).

| Setting | Default | Effect |
|---|---|---|
| `database_url` | `postgresql://agent_analytics:agent_analytics@localhost:5432/agent_analytics` | PostgreSQL connection string. Used by the pool, Alembic and the own-connection helpers in `events.py`. |
| `db_pool_max_size` | `10` | Pool size cap. Fits the database connection limit. |
| `s3_endpoint_url` | `None` | S3 endpoint. `None` = AWS S3. Set it for another S3-compatible store. |
| `s3_region` | `us-east-1` | S3 region. |
| `s3_bucket` | `agent-analytics-inbox` | Inbox bucket. `S3Inbox.ensure_bucket` makes it when it is missing. |
| `s3_access_key_id` | `None` | S3 access key. |
| `s3_secret_access_key` | `None` | S3 secret key. |
| `ingest_chunk_bytes` | `64 * 1024` | Read size for each S3 read in `_read_raw`. |
| `max_decompressed_bytes` | `20 * 1024**3` | A file larger than this after gunzip fails (`ObjectTooLarge`). |
| `ingest_bytes_per_day` | `20 * 1024 * 1024 * 1024` | Byte quota for each site. `quota.bytes_received_last_day` reads the used bytes. Limit check is in the `/ingest` route. |
| `raw_retention_days` | `7` | Age after which cleanup deletes raw objects and `bucket_objects` marks. |
| `events_retention_days` | `30` | Age after which cleanup drops `events` partitions and retention prunes derived tables. |

Test setting: `TEST_DATABASE_SERVER_URL` (default: dev server on `localhost:55432`).

Constants in store code:

| Constant | Value | File | Effect |
|---|---|---|---|
| `PARTITION_LOCK_TIMEOUT` | `2s` | `events.py` | `lock_timeout` for partition create. |
| `DETACH_LOCK_TIMEOUT` | `5s` | `events.py` | `lock_timeout` for partition detach. |
| `DETACH_STATEMENT_TIMEOUT` | `60s` | `events.py` | `statement_timeout` for partition detach. |
| `MAX_REJECTS_PER_FILE` | `10_000` | `import_files.py` | Reject rows kept for each file. |
| `MAX_REASON_CHARS` | `200` | `import_files.py` | Reject reason length. |
| `MAX_LINE_CHARS` | `64 * 1024` | `inbox.py` | Longest line. |
| `DECOMPRESS_CHUNK` | `1024 * 1024` | `inbox.py` | Gunzip output piece. |
| `part_bytes` (`S3Inbox` argument) | `8 * 1024 * 1024` | `inbox.py` | Multipart upload part size. |
| `DEFAULT_SLOW_INTERVAL` | 6 hours | `work.py` | Slow-lane interval. |
| `SLOW_RETRY_AFTER` | 15 minutes | `work.py` | Retry delay after a failed slow run. |
| `LOCK_SKIP_RETRY` | 5 minutes | `work.py` | Retry delay when the slow lock was busy. |
| `MAX_SESSION_HOURS` | `24` | `views.py` | Longest session. |

## Interfaces

Every function is `async` and takes `conn: AsyncConnection` first, unless noted. Rows come back as `dict` (`dict_row`) unless noted.

### Connection (`src.store.db`)

| Function | Notes |
|---|---|
| `open_pool(settings: Settings) -> None` | Opens `AsyncConnectionPool` (`max_size=db_pool_max_size`, `TimeZone=UTC`). Called by `src/main.py`, `src/cli.py`, `src/services/pipeline/worker.py`. |
| `close_pool() -> None` | Closes the pool. |
| `pool() -> AsyncConnectionPool` | Raises `RuntimeError` when the pool is not open. |
| `connection()` | Async context manager. One transaction. Use `async with db.connection() as conn:`. |

### Inbox (`src.store.inbox`)

| Name | Notes |
|---|---|
| `Inbox` (abstract) | `ensure_bucket()`, `put_stream(key, chunks) -> (sha256_hex, size)`, `open_lines(key) -> AsyncIterator[str]`, `delete(key)` (no error when missing). |
| `S3Inbox(settings, client=None, part_bytes=8 MiB)` | Implements `Inbox`. Also `put_stream(key, chunks, max_bytes=None)` (raises `ObjectTooLarge`), `list_objects(prefix="", bucket=None) -> list[dict]` (`key`, `size`, `last_modified`, `etag`), `copy_from(bucket, key, dest_key=None) -> (sha256_hex, size)`. |
| `get_inbox() -> Inbox` | Cached `S3Inbox` from settings. |
| `ObjectNotFound`, `ObjectTooLarge` | Errors. |
| `is_missing(error: ClientError) -> bool` | True for `NoSuchKey`, `404`, `NotFound`, `NoSuchBucket`. |
| `GZIP_MAGIC`, `MAX_LINE_CHARS` | Used by ingest and the importer adapters. |

### `import_files.py`

`insert_new(conn, site_id, source, key, sha256, size, priority, entry="ingest") -> str | None`, `get_file`, `get_by_sha`, `claim_next_file(conn, site_id, allow_backfill=True)`, `mark_success(conn, file_id, counts, min_ts, max_ts)`, `mark_failed(conn, file_id, error)`, `save_progress(conn, file_id, lines_done, counts, min_ts, max_ts)`, `release_file(conn, file_id, error, max_retries, count=True) -> bool`, `reset_files(conn, ids) -> bool`, `force_reimport(conn, file_id) -> bool`, `delete_file`, `origin_partners`, `cdn_partners`, `add_rejects(conn, file_id, rejects) -> int`, `list_rejects`, `list_files`, `count_files`, `files_waiting`, `live_work_waiting`, `sites_with_new_files`, `expired_success_files(conn, retention_days, now=None)`, `mark_deleted`, `last_received_by_source`, `overlapping_files`, `known_bucket_marks`, `remember_bucket_mark`, `prune_bucket_marks(conn, older_than_days)`.

### `events.py`

| Function | Notes |
|---|---|
| `EVENT_COLUMNS` | Column order of the tuples for `copy_events`. |
| `copy_events(conn, rows, imported_at=None) -> int` | Rule ST.5. Makes missing partitions first. |
| `ensure_partitions(conn, days: Iterable[date]) -> None` | Rules ST.1 and ST.2. |
| `drop_old_partitions(keep_days: int) -> int` | Rule ST.3. Returns the number of dropped partitions. |
| `delete_file_events(conn, site_id, file_id) -> int` | Deletes rows with `file_id`. |
| `delete_file_rows(conn, site_id, file_id) -> int` | Deletes rows with `file_id` or `origin_file_id`. |
| `count_events(conn, site_id) -> int` | Row count. |

### Pairing, verify, classify

- `pairing.pair_pending(conn, site_id, window_seconds) -> int`: repeats `PAIR_ROUND` until a round pairs nothing.
- `pairing.expire_pending(conn, site_id, cutoff, hard_cutoff) -> (single, bypass)`.
- `verdicts.current_verdict(conn, site_id, client_key, edge_signal)`, `append_verdict(conn, row) -> int`, `verdicts_without_class`, `pending_client_groups(conn, site_id)`, `assign_events_verdict(conn, site_id, client_key, edge_signal, verdict_id, min_ts, max_ts) -> int`.
- `classify.fetch_unclassified`, `save_classes(conn, rows) -> int`, `save_class(...)`, `classified_summary`.
- `ip_lists.save_snapshot(conn, source, version, prefixes) -> bool`, `latest_snapshot`, `latest_versions`, `ip_in_prefixes(conn, source, version, ip) -> bool`.

### Views and recommendations

- `views.stage_new_events(conn, site_id, now, gap_max_minutes)`, `stage_sessions(conn, site_id, p)`, `session_ips(conn)`, `finish_sessions(conn, site_id, p, shared_ips, base_gaps)`, `close_idle_sessions(conn, site_id, now, gap, agent_gap, margin) -> int`, `refresh_hours(conn, site_id, p) -> int`, `mark_in_views(conn, site_id) -> int`, `reset_site(conn, site_id) -> int`. Details of the incremental design are in the comment at the top of `views.py` and in [../activity-reconstruction/README.md](../activity-reconstruction/README.md).
- `recommendations.py`: pattern queries `p1_product_discovery` to `p5_full_journey`, `class_status`, `agents_for_sessions`, `time_pattern`, `journey_funnel`, `count_events`, `sample_events`, `event_ids`, `create_run`, `finish_run`, `previous_items`, `insert_recommendations`, `cached_text`, `save_cached_text`.

### Pipeline support

- `runs.py`: `start_run(conn, site_id, lane) -> str`, `finish_run(conn, run_id, status, failed_step=None, error=None, counts=None)`, `running_runs_started_before`, `fail_running_run`, `last_success_by_lane`, `consecutive_failures`, `recent_runs`.
- `work.py`: `ensure_site_work`, `take_due_site(conn, lane, now, site_ids=None, slow_interval=...) -> str | None` (claim: `for update skip locked`), `record_run(conn, site_id, lane, success)`, `release_slow`.
- `locks.py`:
  - `lock_key(site_id, lane) -> int` (first 8 bytes of SHA-256, signed).
  - `site_lane_lock(conn, site_id, lane)`: session-level, yields `True` or `False`.
  - `try_site_lane_xact_lock(conn, site_id, lane) -> bool`: transaction-level, same key, so the two exclude each other.
  - `bucket_lock_key(site_id, bucket, prefix) -> int` and `advisory_lock(conn, key)`: session-level.
- `alerts.py`: `raise_alert(conn, site_id, kind, source, message) -> int | None` (`None` when an open alert exists), `resolve_alert -> bool`, `list_alerts(conn, site_id=None, open_only=False, limit=50)`.
- `quota.bytes_received_last_day(conn, site_id, now) -> int`: sums `size_bytes` of `import_files` with `entry = 'ingest'` in the last day. Uploads, CLI files and bucket copies do not count.
- `retention.prune_older_than(conn, cutoff) -> dict[str, int]`: deletes old rows of `page_stats`, `journey_steps`, `agents`, `session_events`, `sessions`, `pipeline_runs` (not `running`) and `import_rejects` (of old files). Returns row counts for each table.

### Dashboard reads (`queries.py`)

`Filters` (dataclass) and the read functions `overview_numbers`, `traffic_by_class_confidence`, `trend`, `top_agents`, `top_pages`, `source_counts`, `freshness`, `open_alerts`, `list_events`, `get_event`, `list_sessions`, `get_session`, `list_agents`, `get_agent`, `list_pages`, `get_page`, `list_journeys`, `latest_run`, `previous_run_id`, `run_change_counts`, `list_recommendation_runs`, `list_recommendations`, `get_recommendation`, `list_pipeline_runs`, `get_pipeline_run`, `previous_window`, `valid_status`. The routes in `apps/api/src/routes/` call them. See [../api/README.md](../api/README.md).

### Database objects

Tables: see [schema.md](schema.md). SQL function: `ensure_events_partition(day date) returns text`.

## Known limits

- Retention drops whole days only. A partition older than `events_retention_days` goes. There is no row-level delete of old `events`.
- Only `events` is partitioned. Retention uses `DELETE` on the derived tables (`retention.prune_older_than`). `open_sessions` is not pruned.
- A partition is dropped only when the detach gets its lock in time. Else it stays until the next cleanup run.
- Size figures (S.1) are design estimates for a site with 10 M lines/day. They are not measurements.
- ClickHouse and TimescaleDB (S.5) are not built. They need a measured trigger.
- Rows of `import_files` are never deleted by retention. Only `delete_file` removes one.

## Open questions

None.

## How to change

### Add a table or column

1. Add a file in `apps/api/migrations/versions/`. Name it `NNNN_slug.py`. Use the next number.
2. Set `revision = "NNNN"` and `down_revision` to the previous revision. Copy the style of `0004_view_fixes.py` (`UP` and `DOWN` lists, loops in `upgrade` and `downgrade`).
3. Write raw SQL with `op.execute`. Write `DOWN` in reverse order.
4. For a new table, add it to the expected set in `test_schema_has_all_tables` (`apps/api/tests/foundation/test_infra.py`).
5. Add the table and its owner to [schema.md](schema.md). Update the file index in `apps/api/src/store/README.md` if you add a store file.
6. If the column has a closed set of values, add the same values to the enum in `apps/api/src/models/domain.py` (rule ST.10).
7. Run `uv run alembic upgrade head`. Run `uv run pytest tests/foundation`.

Do not edit an old migration that other databases already ran. Add a new one.

### Add a query or a write

1. Add the function in the store file of the owning table. Take `conn` first.
2. Use `psycopg` parameters (`%s` or `%(name)s`). Do not build values into the SQL string.
3. Filter `events` by `site_id` and a `ts` range when you can: Postgres then prunes partitions.
4. Call it from the service or route. Never run SQL there.

### Change the events partition or retention

- Partition create: change `ensure_events_partition` in a new migration (do not edit `0005`). Keep `ATTACH` (rule ST.1).
- Retention horizon: change `events_retention_days` (partitions and derived tables) or `raw_retention_days` (raw objects, `bucket_objects`) in `settings.py`.
- Detach and drop logic: `events.drop_old_partitions`. The caller is `drop_expired_partitions` in `apps/api/src/services/cleanup/service.py`.

### Use another S3-compatible store

Set `s3_endpoint_url`, `s3_access_key_id` and `s3_secret_access_key`. For a new storage type, add a class that implements `Inbox` and change `get_inbox`. Use `MemoryInbox` (`apps/api/tests/fakes.py`) as the example of a small implementation.

### Move `events` to another store (S.5)

Change `events.py` and `views.py` only (S.3). Keep the "newest version of row" shape (S.4). Keep metadata, `verdicts` and runs in Postgres.

## Tests

| Path | Covers |
|---|---|
| `apps/api/tests/foundation/test_infra.py` | All tables exist, partition function is idempotent, dedupe index, factories, fixtures, `MemoryInbox`. |
| `apps/api/tests/foundation/test_import_files_store.py` | `insert_new` and the unique hash, claim order, `SKIP LOCKED`, counters, rejects cap, `force_reimport`, paging, `expired_success_files`, `overlapping_files`. |
| `apps/api/tests/conftest.py` | A fresh database for each pytest session, migrated with `alembic upgrade head`. Truncate before each test. |

Run from `apps/api`. Tests need Postgres on port 55432 (see `apps/api/README.md`):

```
uv run pytest tests/foundation
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

## Related modules

- [../ingestion/README.md](../ingestion/README.md): writes `import_files`, reads the byte quota, calls the inbox.
- [../pairing/README.md](../pairing/README.md): `events` pair columns.
- [../verification/README.md](../verification/README.md): `verdicts`, `ip_list_snapshots`.
- [../classification/README.md](../classification/README.md): class columns of `verdicts`.
- [../activity-reconstruction/README.md](../activity-reconstruction/README.md): sessions and hourly rollups.
- [../recommendations/README.md](../recommendations/README.md): recommendation tables.
- [../pipeline/README.md](../pipeline/README.md): runs, `site_work`, locks, alerts, cleanup, retention.
- [../api/README.md](../api/README.md): routes that call `queries.py`.
- [../architecture/README.md](../architecture/README.md): where the store sits in the system.
- [../deployment/README.md](../deployment/README.md): the `migrate` service and the Postgres and S3 services.
- [../testing/README.md](../testing/README.md): test setup.
