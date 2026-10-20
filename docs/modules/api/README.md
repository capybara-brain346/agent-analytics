# API (FastAPI app, routes, CLI, settings)

This module is the back-end application surface. It has the FastAPI app (`src/main.py`), every HTTP route, the Typer CLI (`src/cli.py`), the JSON logger and the settings (`src/config/settings.py`).
Input: HTTP requests, CLI commands and environment variables. Output: JSON responses, pipeline runs started by hand, and JSON log lines on stdout.
This file is the central settings reference. Other modules link here for setting names and defaults.

## Read this when

- You add, change or remove an HTTP route or a query parameter.
- You change an error code, a response shape or the auth rule.
- You add a CLI command or change a CLI option.
- You add or change a setting (environment variable) or its default.
- You need the exact name, default or effect of a setting.
- You change the log format or add log fields.
- An AI agent or script must read the same data as a dashboard screen.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/main.py` | `create_app()`, `app`, `lifespan`: opens and closes the DB pool, logs the `API_TOKEN` warning. |
| `apps/api/src/routes/__init__.py` | `root_router` (open routes) and `api_router` (mounted at `/api`, token-guarded). `API_MODULES` lists the `/api` modules. |
| `apps/api/src/routes/auth.py` | `bearer()`, `require_api_token()`: guards `/api/*`. |
| `apps/api/src/routes/params.py` | Shared dependencies: `Conn`, `Site`, `ScopeDep`, `PagingDep`, `error()`, `not_found()`, `pct()`. |
| `apps/api/src/routes/health.py` | `GET /livez`, `GET /health`. |
| `apps/api/src/routes/metrics.py` | `GET /metrics` (Prometheus). |
| `apps/api/src/routes/ingest.py` | `POST /ingest`, plus the shared helpers `store_body()`, `load_site()`, `source_for()`, `inbox_dependency()`. |
| `apps/api/src/routes/overview.py` | `GET /api/overview`. |
| `apps/api/src/routes/recommendations.py` | `/api/recommendations*`. |
| `apps/api/src/routes/agents.py` | `/api/agents*`. |
| `apps/api/src/routes/events.py` | `/api/events*`. |
| `apps/api/src/routes/sessions.py` | `/api/sessions*`. |
| `apps/api/src/routes/pages.py` | `GET /api/pages`. |
| `apps/api/src/routes/journeys.py` | `/api/journeys*`. |
| `apps/api/src/routes/imports.py` | `/api/imports*`. |
| `apps/api/src/routes/runs.py` | `/api/runs*`. |
| `apps/api/src/routes/sites.py` | `GET /api/sites`. |
| `apps/api/src/routes/errors.py` | `not_implemented()` helper. |
| `apps/api/src/models/api.py` | Response models: `Paged[T]`, `PageInfo`, `Window`, `Label`, `CLASS_NAMES`, `PATTERN_NAMES`, `ErrorBody`, and one model per screen. |
| `apps/api/src/cli.py` | Typer app: every CLI command. |
| `apps/api/src/config/settings.py` | `Settings`, `get_settings()`: every setting and default. |
| `apps/api/src/logger/__init__.py` | `configure_logging()`, `get_logger()`, `JsonFormatter`. |
| `apps/api/.env.example` | Local development values. |
| `apps/api/Dockerfile` | One image. Default command: `uvicorn src.main:app --host 0.0.0.0 --port 8000 --no-access-log`. |
| `apps/api/tests/api/` | API tests (one file for each screen, plus `test_auth.py`, `test_params.py`). |
| `apps/api/tests/test_app.py` | App smoke test (`/livez`, `/metrics`). |
| `apps/api/tests/pipeline/test_cli.py`, `test_health.py` | CLI wiring and `/health` tests. |
| `apps/api/tests/ingest/` | `/ingest` and `/api/imports` route tests. |

The route modules are thin. They read parameters, call `src/store/queries.py` or a service, and map the result to a model in `src/models/api.py`. They contain no SQL.

## Data flow

```
 Sender (Vector / CDN push)                     Dashboard UI / AI agent / script
        | POST /ingest  (site token)                    | GET /api/*  (Bearer API_TOKEN)
        v                                               v
 +------------------+                          +----------------------+
 | routes/ingest    |                          | routes/* (read-only) |
 | rate + quota     |                          | params.py: site,     |
 +--------+---------+                          | range, class, paging |
          | raw body (stream)                  +----------+-----------+
          v                                               | Filters
   S3 inbox + import_files row                            v
          |                                      store/queries.py
          v                                               | SQL rows
   worker (pipeline module)                               v
          | events, verdicts, views             response models (JSON, labels)
          v                                               |
      Postgres  <---------------------------------------+
          ^
          | CLI: import / run-pipeline / run-recommendations / cleanup
   Typer CLI (src/cli.py)  <--- operator
```

Request sequence for one `/api` call:

```
 Client            FastAPI app         auth.py          params.py         store/queries     Postgres
   | GET /api/x?..   |                    |                 |                  |               |
   |---------------->|  require_api_token |                 |                  |               |
   |                 |------------------->| compare token   |                  |               |
   |                 |<-------------------| 401 if bad      |                  |               |
   |                 |  resolve site, range, class, paging   |                  |               |
   |                 |-------------------------------------->| 404/422 if bad   |               |
   |                 |  query(conn, Filters)                 |                  |               |
   |                 |------------------------------------------------------->| SELECT        |
   |                 |<-------------------------------------------------------|<--------------|
   | 200 JSON        |  map rows to response model           |                  |               |
   |<----------------|                                       |                  |               |
```

## Rules and decisions

### Agent-first API

1. [A1] The JSON API is a first-class user. Every dashboard screen has a JSON route with the same filters and the same IDs. Why: Webzero is agent-first. An agent must read the same data as a human without the UI.
2. [A2] The UI path and the API path match. The API path is the UI path under `/api`. Exceptions: `/data/imports` is `/api/imports`, `/data/runs` is `/api/runs`, and `/data/health` is `/health` (no `/api` prefix, no token). Why: a link from a human and a call from an agent reach the same record.
3. [A3] IDs are the same as in the UI: recommendation IDs, session IDs, event IDs, agent IDs, journey IDs, run IDs. Why: A2.
4. [A4] Global filters are query parameters: `site`, `from`, `to`, `class` (UX rule R8). Why: filters stay the same between screens and in shareable links.
5. [A5] Labels are lowercase: `"label": "observed" | "inferred" | "unknown"` (type `Label` in `src/models/api.py`). A numeric or fact value carries `label` in its model. Text fields that are inferred or unknown use `LabeledText`. Why: UX rule R1 (every statement has a label).
6. [A6] JSON keys are `snake_case`. Times are ISO 8601 in UTC. Why: one format for every consumer.
7. [A7] Lists that can grow are paged with `Paged[T]` (`items`, `page: {limit, offset, total, next_offset}`) and have a stable sort. Parameters: `limit` 1..200 (default 50), `offset` >= 0. Why: an agent can walk a list with `next_offset`.
8. [A8] Drill-down: a number in a response links to a list that can show the rows behind it. Example: `VerdictRow.events_link` is `/api/events?site=<site>&verdict_id=<id>`. Why: UX rule R2 (every number is a link).
9. [A9] Task outcome is never "success". Responses show "reached step N". The outcome field is `unknown`. Why: UX rule R6 (a 200 is not success).
10. [A10] A claimed agent name carries a verification note ("claims to be X, unverified") until the verdict is `VERIFIED`. Why: UX rule R3.

### Auth and open routes

11. [B1] `/api/*` needs `Authorization: Bearer <API_TOKEN>` when `API_TOKEN` is set. The compare is constant-time (`hmac.compare_digest`). A bad or missing token gives `401` with `WWW-Authenticate: Bearer`. Why: protect read access and the three state-changing routes.
12. [B2] If `API_TOKEN` is not set, `/api/*` is open. The API logs a warning at start. Set `API_TOKEN` in every shared environment, or expose only `/ingest` at the ingress. Why: development must work with no setup.
13. [B3] `/ingest` uses a per-site token (not `API_TOKEN`). `/livez`, `/health` and `/metrics` are open. Why: senders and probes must not hold the dashboard token.
14. [B4] `/ingest` gives the same `401` for an unknown site and a bad token. Why: the route must not reveal site IDs.

### State-changing routes

15. [C1] Only three `/api` routes change state: `POST /api/imports/upload`, `DELETE /api/imports/{file_id}` and `POST /api/recommendations/generate`. All other `/api` routes are read-only. Why: the API is a read model of the pipeline output.
16. [C2] `/ingest` and `/api/imports/upload` write only to the S3 inbox and `import_files`. They do not parse. The worker imports the file later (decisions 1.3, 1.15). Why: a slow parser must not block senders.
17. [C3] [1.15] `POST /ingest?site=<id>`: bearer token for each site. The body streams to the inbox in `INGEST_CHUNK_BYTES` parts (not `UploadFile`). The sha256 is computed during the stream. The route inserts an `import_files` row (status `new`) and replies `202`. Body limit is `INGEST_MAX_BYTES`. Why: Vector `http` and CDN HTTP push support only this method. Memory stays flat.
18. [C4] A duplicate body (same sha256 for the site) returns `200` with `duplicate: true`. Why: sender retries must be safe. The unique constraint on `import_files.sha256` (S.6) decides.
19. [C5] [1.16] `/ingest` has a rate limit and a byte quota for each site. Over the limit gives `429` with `Retry-After`; the sender keeps the data and retries. Rate limit: `INGEST_RATE_PER_MINUTE`, sliding window in process memory (`Retry-After: 60`). Byte quota: `INGEST_BYTES_PER_DAY`, read from Postgres as the sum of `import_files.size_bytes` for `entry = 'ingest'` in the last 24 h (`Retry-After: 3600`). Why: one tenant cannot flood the system, and no data is lost. The quota is shared by all API replicas. The rate window is not: with N replicas the real limit is up to N times the setting.
20. [C6] `POST /api/imports/upload` uses the streamed body with limit `UPLOAD_MAX_BYTES` (2 GB), file priority `backfill` and entry `upload`. It has no rate limit and no quota. Why: dashboard upload is for old logs; backfill must not delay live data (decision 1.18). Later: presigned multipart upload.
21. [C7] [1.21] `DELETE /api/imports/{file_id}` runs `importer.delete_import()`: one transaction under the site's fast-lane lock. It deletes the file's events (also paired rows that hold its origin lines), resets paired partner files to `new`, deletes the file row, deletes all views of the site, and sets `in_views = false` on its events. The raw file is deleted after the commit. It returns `404` for an unknown file, and `409` during a run, during an import, or when a partner's raw file is gone. Why: a paired row holds lines of two files, and the incremental views only add, so a full rebuild of the site is the only correct result. The freed sha256 lets the same file load again.
22. [C8] `POST /api/recommendations/generate` runs the slow lane for the site now (`pipeline.run_recommendations`). It returns `409 lock_taken` when a run is active, and `500 run_failed` on failure (the previous list stays valid). Why: same as the dashboard button "Generate now" (decision 7.1).

### Parameters and errors

23. [D1] `site` is optional when exactly one site exists. With many sites it is required (`422 site_required`). An unknown site gives `404 site_not_found`. Why: easy for one-site setups, strict for many.
24. [D2] Default time range: `to` = now, `from` = `to` minus 24 h. `from` must be earlier than `to` (`422 bad_range`). Naive times are read as UTC. Why: one default for every screen.
25. [D3] `class` takes values 1..6, repeated (`class=1&class=2`) or comma list (`class=1,2`). Bad value gives `422 bad_class`. Why: the 6 classes are fixed.
26. [D4] Errors from route code use `{"detail": {"code": "<code>", "message": "<text>"}}` (`params.error()`). Not-found errors have code `<what>_not_found`. Why: an agent reads `code`, not text.
27. [D5] `GET /health` returns `503` when any lane is unhealthy, and the same body. Why: probes read the status code; people read the body.
28. [D6] Time-based values come from the database in UTC. DB sessions use `-c TimeZone=UTC` (`src/store/db.py`). Why: `date_trunc` and casts must not depend on the server time zone.

### Health and alerts

29. [7.6] `/health` returns the last success of each lane. A lane is unhealthy when its last success is older than `HEALTH_STALE_MINUTES` (fast lane), or older than the slow interval plus `HEALTH_STALE_MINUTES` (slow lane). A lane that never succeeded is unhealthy. Open alerts are in the body (up to 100). A raised alert after `FAILED_RUNS_ALERT` failed runs in a row comes from the pipeline module. Why: PDF section 05 health checks. Phase 2 uses `/health`.
30. [7.11] `/health` and the staleness rule apply for each site and lane. Why: many sites in one system.
31. [E1] A database error in `/health` gives `503` with `healthy: false`, empty `lanes` and empty `alerts`. The error is logged. Why: a probe must get an answer even when the DB is down.

### CLI

32. [F1] [1.1] [1.2] The CLI is an entry point for old logs, demos, tests and handover. `import --now` imports at once with the same code as the worker. Why: demo and tests must not wait for the scheduler.
33. [F2] The CLI keeps the manual lane commands (`run-pipeline`, `run-recommendations`). The trigger in production is the worker loop (decision 7.1). Why: the back end owns the logic; the CLI only calls it.
34. [F3] [1.9] `import --force` bypasses the sha256 check. Why: fix an adapter bug, then import the file again.
35. [F4] [1.20] Without `--site` and `--source`, `import` reads both from the file name `<site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log[.gz]` (`importer.parse_log_name`). Why: a dropped file gives only its name.
36. [F5] CLI imports use file priority `backfill` and entry `cli`. Why: decision 1.18.

### Logger

37. [G1] Logs are JSON lines on stdout. Fields: `ts` (ISO 8601 UTC), `level`, `logger`, `msg`. Fields passed with `extra=` become top-level keys (for example `site_id`, `run_id`, `step`). An exception adds `exc`. Why: one log format for every process; log tools parse it.
38. [G2] `configure_logging(level)` is called once at start: in `lifespan` (API) and in the Typer callback (CLI). The `uvicorn*` loggers propagate to the root handler. The Dockerfile starts uvicorn with `--no-access-log`. Why: one handler, no duplicate lines.
39. [G3] The package is `src/logger`, not `logging`. Why: `logging` is a standard library module.
40. [G4] Logs and error messages never contain raw log lines. Rejected import lines keep only the line number and reason (decision 1.7). Why: hostile input.

### Configuration

41. [H1] Every configurable value lives in `Settings` (`src/config/settings.py`). Code imports it with `get_settings()` (cached with `lru_cache`). Why: one place for defaults (project rule).
42. [H2] Settings come from environment variables and an optional `.env` in the working directory. The env var name is the field name in upper case. Unknown variables are ignored (`extra="ignore"`). Why: pydantic-settings rule used by `Settings`.
43. [H3] Tests ignore `apps/api/.env`: `tests/conftest.py` sets `Settings.model_config["env_file"] = None`. Only process environment variables apply. Why: a developer's `.env` must not change test results.
44. [H4] YAML data (bot registry, IP lists, CDN field maps, site configs) is not a setting. `CONFIG_DIR` only points to it. A new bot or CDN is a data change. Why: no code change for data.

## Routes

Auth: `Open` = no token. `Site token` = per-site token. `API token` = `Authorization: Bearer <API_TOKEN>`, or open if `API_TOKEN` is not set.

### Open routes (mounted at `/`)

| Method and path | Auth | Parameters | Response |
|---|---|---|---|
| `GET /livez` | Open | none | `{"status": "ok"}` |
| `GET /health` | Open | none | `HealthReport`: `healthy`, `lanes[]` (`site_id`, `lane`, `last_success`, `healthy`), `alerts[]` (`id`, `site_id`, `kind`, `source`, `message`, `raised_at`). `200` if healthy, else `503`. |
| `GET /metrics` | Open | none | Prometheus text. Metrics in code: `pipeline_runs_total{lane,status}`, `import_files_waiting`. |
| `POST /ingest` | Site token | `site` (required), `source` (`cdn`/`origin`; optional when the site has one source) | `IngestAccepted`: `file_id`, `duplicate`. `202` new, `200` duplicate. Body = raw log bytes (plain or gzip). |

`/ingest` errors: `401` bad token or unknown site, `422` bad source, `429` rate or quota (with `Retry-After`), `413` body too large (by `Content-Length` or by stream), `400` empty body. These errors use a plain string `detail`.

### Dashboard routes (mounted at `/api`, API token)

Common parameters:

- Scope (`ScopeDep`): `site`, `from`, `to`, `class`. See D1 to D3.
- Site only (`Site`): `site`.
- Paging (`PagingDep`): `limit` (1..200, default 50), `offset` (default 0).

| Method and path | Parameters | Response | Dashboard screen |
|---|---|---|---|
| `GET /api/sites` | none | `list[str]`: site IDs, sorted | Site picker |
| `GET /api/overview` | Scope; `bucket` = `hour`/`day` (default `hour`) | `Overview`: `window`, `empty`, `freshness`, `key_numbers`, `traffic_by_class`, `unclassified_requests`, `trend`, `top_agents` (5), `top_pages` (10), `top_recommendations` (3, no `gone`), `coverage`, `open_alerts_count`, `open_alerts` | Overview |
| `GET /api/recommendations` | Site; `run` (run ID, default latest), `pattern` (`P1`..`P5`), `confidence` (`high`/`medium`/`low`), `change` (`new`/`open`/`gone`) | `RecommendationList`: `run` (`RunHeader` or null), `empty_reason` (`no_run`/`no_candidates`/null), `items`, `gone` | Recommendations |
| `GET /api/recommendations/runs` | Site; Paging | `Paged[RunHeader]` | Run history |
| `POST /api/recommendations/generate` | Site; `window` (`^\d+[hd]$`, default `6h`) | `GenerateResult`: `status` = `completed`, `run`. Errors: `409 lock_taken`, `500 run_failed`. | "Generate now" button |
| `GET /api/recommendations/{rec_id}` | Site | `RecommendationDetail`: item fields, `reason`, `evidence`, `potential_issue`, `suggested_validation`, `next_action`, `model`, `prompt_version`, `text_source_note`, `fact_bundle`, `history`, `first_seen_run_id`, `related`, `run` | Recommendation detail |
| `GET /api/agents` | Scope; `verification` (`VERIFIED`/`CLAIMED`/`UNVERIFIED`/`SPOOFED`/`UNKNOWN`), `q` (name contains) | `list[AgentRow]` | Agents |
| `GET /api/agents/{agent_id}` | Scope | `AgentDetail`: `agent`, `why_this_class`, `verdict_history`, `client_keys`, `activity`, `top_paths`, `status_mix`, `sessions`. Header uses the latest hourly row; totals use the range; the `class` filter does not apply to the header. | Agent detail |
| `GET /api/events` | Scope; Paging; `agent`, `path` (contains), `status` (`403`, `4xx` or comma list), `verdict`, `verdict_id`, `confidence`, `client_key`, `session`, `source` (`origin`/`cdn`/`paired`), `import_file` (UUID) | `Paged[EventRow]` | Activity Explorer, Events tab |
| `GET /api/events/{event_id}` | Site | `EventDetail`: `request`, `source`, `verdict`, `classification`, `session` (`session_id`, `position`, `of`), `import_file`, `recommendations` | Event detail |
| `GET /api/sessions` | Scope; Paging; `agent`, `confidence`, `state` (`in_progress`/`closed`), `has_retry`, `has_loop`, `reached_conversion`, `journey` (journey ID), `reached_step` (>= 1), `client_key` | `Paged[SessionRow]` | Sessions tab |
| `GET /api/sessions/{session_id}` | Site | `SessionDetail`: `session`, `facts`, `grouping`, `confidence_reason`, `steps` (with `flags`: `retry`, `loop`, `key_page`, `conversion_page`), `outcome`, `gaps`, `recommendations` | Session detail |
| `GET /api/pages` | Scope; `view` (`agent_heavy`/`errors`/`blocks`/`retries`/`never_reached`); `path` (exact path) | Without `path`: `PageList` (`view`, `items`). With `path`: `PageDetail` (`page`, `in_sitemap`, `access_policy` = `allowed`/`blocked_by_intent`, `by_class`, `over_time`, `agents`, `sessions`, `recommendations`). | Pages tab, Page detail |
| `GET /api/journeys` | Scope | `list[JourneyOut]` | Journeys tab |
| `GET /api/journeys/{journey_id}` | Scope | `JourneyOut`: `journey_id`, `critical`, `steps`, `by_class[]` (`reached`, `stopped_at`, `retry_or_loop`), `outcome` (`unknown`) | Journey detail |
| `GET /api/imports` | `site` (optional; no default), `status`, `limit`, `offset` | `ImportList`: `items[]` (`ImportFile`, with `overlap_warning` and `delete_on`), `total`, `limit`, `offset` | Data and Pipeline: import runs |
| `POST /api/imports/upload` | `site` (required), `source` (optional if one source). Body = raw log bytes. | `IngestAccepted`. `202` new, `200` duplicate. | Dashboard upload |
| `DELETE /api/imports/{file_id}` | `file_id` (UUID) | `ImportDeleted`: `file_id`, `site_id`, `events_deleted`, `files_reimported`. `404`, `409`. | Delete import |
| `GET /api/runs` | Site; Paging; `lane` (`fast`/`slow`), `status` (`running`/`success`/`failed`) | `Paged[PipelineRunOut]` | Data and Pipeline: pipeline runs |
| `GET /api/runs/{run_id}` | Site; `run_id` (UUID, else `422 bad_run_id`) | `PipelineRunOut` | Run detail |

Notes on specific routes:

- Recommendation run IDs are integers (`recommendation_runs.id`). Pipeline run IDs are UUID strings (`pipeline_runs.id`). Do not mix them.
- `/api/recommendations` returns `gone` items in a separate list. `items` never holds `gone` rows.
- `/api/pages` adds key pages, conversion pages and sitemap pages with 0 requests when no client reached them. Tags `key` and `conversion` come from the site config.
- `/api/sessions/{session_id}` marks a session `in_progress` with `last_event_age_seconds`. Retry and loop flags use `RETRY_WINDOW_SECONDS` and `LOOP_REPEAT_COUNT`.
- `/api/overview` `freshness.state` is one of `ok`, `updating`, `last_run_failed`, `alert_failing`, `alert_no_data`, `no_runs` (banner states of the dashboard).
- `/api/overview` `coverage` lists what the logs cannot show (`cannot_see`) and partial data (`partial`). Keep it honest: it implements UX rule R4.

### Error codes (`params.error`)

| HTTP | `code` | Cause |
|---|---|---|
| 404 | `site_not_found` | Unknown `site`. |
| 404 | `<what>_not_found` | `run_not_found`, `recommendation_not_found`, `agent_not_found`, `event_not_found`, `session_not_found`, `page_not_found`, `journey_not_found`, `pipeline_run_not_found`. |
| 422 | `site_required` | No `site` and more than one site. |
| 422 | `bad_range` | `from` is not earlier than `to`. |
| 422 | `bad_class` | `class` is not 1..6. |
| 422 | `bad_status` | `status` filter on `/api/events` is not like `403`, `4xx` or `403,429`. |
| 422 | `bad_import_file` | `import_file` is not a UUID. |
| 422 | `bad_run_id` | Pipeline run ID is not a UUID. |
| 409 | `lock_taken` | `POST /api/recommendations/generate` while a run is active. |
| 500 | `run_failed` | Recommendation run failed. |
| 401 | none (string detail) | Bad `API_TOKEN` or site token. |
| 422 | none | FastAPI validation error for a pattern or range rule (for example `pattern`, `limit`). |

## Interfaces

### CLI

Run with `uv run python -m src.cli <command>` from `apps/api`. The container runs `python -m src.cli worker`. `no_args_is_help=True`.

| Command | Options | Effect and exit codes |
|---|---|---|
| `worker` | `--lanes fast\|slow\|all` (default `all`) | Runs `pipeline.run_forever(lanes)`. Details of the loops: [pipeline](../pipeline/README.md). |
| `run-pipeline <lane>` | `lane` = `fast`/`slow` (argument); `--site <id>` (required) | Runs one lane for one site now. Prints `run <id>: <status>`. Exit `2` if another run holds the lock. Exit `1` if the run failed (prints `failed at <step>: <error>`). |
| `run-recommendations` | `--site <id>` (required); `--window <e.g. 6h, 14d>` (default `RECOMMENDATION_WINDOW`) | Makes a recommendation run now. Prints `recommendation run <id>`. Exit `1` on lock taken or failure. |
| `import <path>` | `--site <id>`; `--now`; `--force`; `--source cdn\|origin` | Imports one log file, or every `.log`/`.log.gz` file in a folder (name order). Without `--site` and `--source`, they come from the file name. Prints `<name>: <site> <file_id> duplicate\|queued`. Exit `2` for an empty folder or a file with no site. |
| `cleanup` | none | Deletes expired raw files and drops old event partitions (`cleanup.run_cleanup`). |
| `download-ip-lists` | none | Downloads vendor IP lists (`verify.download_snapshots`). In offline mode the bundled files are used. |

Every command calls `configure_logging(LOG_LEVEL)` first. Commands that touch the DB open and close the pool with `run_with_pool()`.

### Python

| Name | Signature or role |
|---|---|
| `src.main.create_app` | `create_app() -> FastAPI`. Includes `root_router` and `api_router` (prefix `/api`). |
| `src.config.get_settings` | `get_settings() -> Settings` (cached). Clear with `get_settings.cache_clear()` in tests. |
| `src.logger.configure_logging` | `configure_logging(level: str = "INFO") -> None`. |
| `src.logger.get_logger` | `get_logger(name: str) -> logging.Logger`. |
| `src.routes.params.error` | `error(status: int, code: str, message: str) -> HTTPException`. |
| `src.routes.params.not_found` | `not_found(what: str, ident: object) -> HTTPException` (code `<what>_not_found`). |
| `src.routes.params.Scope` | Frozen dataclass: `site_id`, `start`, `end`, `classes`. `.filters(**extra)` gives `queries.Filters`. `.window()` gives `Window`. |
| `src.routes.params.Paging` | Frozen dataclass: `limit`, `offset`. `.info(total)` gives `PageInfo`. |
| `src.routes.auth.require_api_token` | FastAPI dependency on `api_router`. |

## Configuration

The env var name is the setting name in upper case. Defaults are from `src/config/settings.py`.
Docker Compose and Helm set these variables: see [deployment](../deployment/README.md).

### General and store

| Setting | Default | Effect |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Log level of the root logger. |
| `DATABASE_URL` | `postgresql://agent_analytics:agent_analytics@localhost:5432/agent_analytics` | PostgreSQL connection string (one database, decision S.1). |
| `DB_POOL_MAX_SIZE` | `10` | Maximum connections in the pool of one process. Keep the total below the database connection limit (decision 7.10). |
| `CONFIG_DIR` | `apps/api/config` | Folder with YAML data: `sites/`, `registry/`, `cdn/`. |
| `OFFLINE` | `false` | `true` = no outside calls: IP lists are not downloaded (bundled files are used) and the daily download job is off. |

### Inbox (S3-compatible storage, decision 1.19)

| Setting | Default | Effect |
|---|---|---|
| `S3_ENDPOINT_URL` | none | Endpoint of the S3-compatible storage. None = AWS S3. |
| `S3_REGION` | `us-east-1` | S3 region name. |
| `S3_BUCKET` | `agent-analytics-inbox` | Inbox bucket. |
| `S3_ACCESS_KEY_ID` | none | S3 access key. |
| `S3_SECRET_ACCESS_KEY` | none | S3 secret key. |

### Dashboard API

| Setting | Default | Effect |
|---|---|---|
| `API_TOKEN` | none | Bearer token for `/api/*`. None = open, and the API logs a warning at start. |

### Ingest (decisions 1.15 to 1.17)

| Setting | Default | Effect |
|---|---|---|
| `INGEST_MAX_BYTES` | `52428800` (50 MB) | Body limit of `POST /ingest`. Over it: `413`. |
| `UPLOAD_MAX_BYTES` | `2147483648` (2 GB) | Body limit of `POST /api/imports/upload`. |
| `INGEST_CHUNK_BYTES` | `65536` (64 KB) | Size of the parts when a body or a CLI file streams to the inbox. |
| `MAX_DECOMPRESSED_BYTES` | `21474836480` (20 GB) | A file larger than this after gunzip fails. |
| `INGEST_RATE_PER_MINUTE` | `120` | Requests for each site and minute at `/ingest` (in-memory sliding window for each process). |
| `INGEST_BYTES_PER_DAY` | `21474836480` (20 GB) | Byte quota for each site and 24 h at `/ingest` (from Postgres, shared by replicas). |

### Bucket reader (decision 1.17)

| Setting | Default | Effect |
|---|---|---|
| `BUCKET_READER_ENABLED` | `false` | `true` = the fast loop reads CDN log buckets that sites declare in `cdn_bucket`. |
| `BUCKET_READER_INTERVAL_SECONDS` | `60` | Time between two bucket reads. |
| `BUCKET_READER_PREFIX` | empty | Default object prefix when the site's `cdn_bucket` has no `prefix`. |

### Worker and pipeline

| Setting | Default | Effect |
|---|---|---|
| `TICK_SECONDS` | `60` | Time between two ticks of a worker loop. |
| `WORK_LIMIT_BYTES` | `209715200` (200 MB) | Import work limit for each run. The rest waits for the next turn (decision 7.9). |
| `WORK_LIMIT_LINES` | `2000000` | Import work limit in lines for each run. |
| `HEALTH_STALE_MINUTES` | `15` | `/health`: a lane with no success for longer than this is unhealthy (slow lane: plus the slow interval). |
| `STALE_RUN_MINUTES` | `30` | A run in status `running` that is older than this and has a free lock is closed as crashed. |
| `FAILED_RUNS_ALERT` | `3` | Failed runs in a row that raise an alert. |

### Import and alerts

| Setting | Default | Effect |
|---|---|---|
| `RAW_RETENTION_DAYS` | `7` | Raw files with status `success` older than this are deleted (decision 1.10). Also used for `delete_on` in `/api/imports`. |
| `EVENTS_RETENTION_DAYS` | `30` | Old event partitions are dropped. Derived tables (hourly rows, sessions, `pipeline_runs`, `import_rejects`) older than this are pruned. Recommendation runs are kept. |
| `NO_DATA_ALERT_MINUTES` | `60` | A site with no new data for this time raises a `no_data` alert. A site file can override it. |

### Pair

| Setting | Default | Effect |
|---|---|---|
| `PAIR_WINDOW_SECONDS` | `5` | Pair window: plus or minus N seconds around the CDN time. |
| `PAIR_WAIT_MINUTES` | `10` | An unpaired event waits this long, then stays single. |
| `PAIR_HARD_LIMIT_HOURS` | `24` | While the other source still has queued files, rows keep waiting, up to this limit. |

### Verify

| Setting | Default | Effect |
|---|---|---|
| `RDNS_TTL_HOURS` | `24` | A reverse-DNS result is valid for this time. |
| `UNVERIFIED_RETRY_MINUTES` | `60` | A DNS error is retried after this time (not after `RDNS_TTL_HOURS`). |
| `DNS_TIMEOUT_SECONDS` | `2.0` | Timeout of one DNS lookup. |
| `IP_LIST_DIR` | `apps/api/config/registry/ip-lists` | Folder with vendor IP list snapshots. |

### Activity reconstruction

| Setting | Default | Effect |
|---|---|---|
| `SESSION_GAP_MINUTES` | `30` | A gap longer than this starts a new session. |
| `AGENT_SESSION_GAP_MINUTES` | `2` | Same, for agent clients (registry category). |
| `DELIVERY_MARGIN_MINUTES` | `10` | A session closes when its last event is older than the gap plus this margin (late CDN files). |
| `RETRY_WINDOW_SECONDS` | `60` | Same client and path again within this time after a 4xx/5xx = retry. |
| `LOOP_REPEAT_COUNT` | `5` | Same path this many times in a session = loop. |

### Recommendations

| Setting | Default | Effect |
|---|---|---|
| `RECOMMENDATION_WINDOW` | `6h` | Window of a recommendation run (`<n>h` or `<n>d`). The slow lane runs once for each window. |
| `P1_MIN_KEY_PAGES` | `3` | P1 threshold: key pages. |
| `P2_MIN_BLOCKS` | `5` | P2 threshold: blocks (403). |
| `P3_MIN_SESSIONS` | `3` | P3 threshold: sessions. |
| `FREQUENCY_MID_MIN` | `5` | Frequency factor: sessions below this = 1. |
| `FREQUENCY_HIGH_OVER` | `50` | Frequency factor: 5 to this value = 2, above = 3. |
| `P4_BYTES_RATIO` | `0.3` | P4: AI median bytes below this share of the browser median. |
| `OPENROUTER_API_KEY` | none | LLM key. None = template text only. |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | LLM gateway URL (OpenRouter or a compatible gateway). |
| `LLM_MODEL` | none | LLM model ID. None = template text only. Both `OPENROUTER_API_KEY` and `LLM_MODEL` must be set to use the LLM. |
| `LLM_PROMPT_VERSION` | `1` | Prompt version stored with the text. |
| `LLM_TIMEOUT_SECONDS` | `30.0` | Timeout of one LLM call. |

### Values in code

| Value | Where | Note |
|---|---|---|
| Maintenance interval (1 day) and retry (1 h) | `src/services/pipeline/worker.py` (`MAINTENANCE_EVERY`, `MAINTENANCE_RETRY`) | Daily jobs: IP list download (not offline), cleanup, derived retention. |
| Retry of a slow-lane site whose lock was taken | `src/store/work.py` (`LOCK_SKIP_RETRY`) | 5 minutes, not a full window. |
| `limit` (default 50, max 200) | `src/routes/params.py` | Paging. |
| Default range (24 h) | `src/routes/params.py` | See D2. |

### `.env.example` (local development)

`apps/api/.env.example` holds: `LOG_LEVEL`, `DATABASE_URL`, `S3_ENDPOINT_URL=http://localhost:8333`, `S3_BUCKET`, `S3_ACCESS_KEY_ID=dev`, `S3_SECRET_ACCESS_KEY=dev-secret`, `OFFLINE=false`. The LLM lines are commented out: `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`. Copy it to `apps/api/.env` for local runs. Compose needs no `.env`.

## Known limits

- No user login. One shared `API_TOKEN` guards `/api/*`, and it is optional. There is no per-user access control. This must change before customer use (PDF section 05).
- The `/ingest` rate window is in process memory. With N API replicas the real limit is up to N times `INGEST_RATE_PER_MINUTE`.
- Error shapes are not uniform. Parameter and not-found errors use `{"code", "message"}`. `/ingest`, `/api/imports*` and auth errors use a string `detail`. FastAPI validation errors use the FastAPI default shape.
- Not every list is paged. `/api/sites`, `/api/agents`, `/api/pages` and `/api/journeys` return the full list. `/api/imports` is paged but has its own shape (`items`, `total`, `limit`, `offset`) instead of `Paged[T]`.
- Not every model carries a `label`. See A5: only the models that define `label` (and `LabeledText`) do.
- `GET /api/imports` has no site default: `site` is optional and means "all sites".
- Logs cannot show task completion. Outcome fields are always `unknown`.
- Raw IPs and full URLs (with query strings) are stored and returned. Redaction is necessary before customer use (PDF sections 05 and 09; decision 1.12).
- The API does not export data and does not push alerts (no email or Slack). See the dashboard module for the UI scope.

## Open questions

- Default time range: 24 h or the recommendation window (6 h)? The API uses 24 h.
- Do "gone" recommendations show by default or only in run history? The API returns them in a separate `gone` list.
- Offline mode (`OFFLINE=true`): confirm it with the customer. Each outside call already has a fallback (IP lists: bundled files; reverse DNS: the customer's DNS server, UNVERIFIED if it cannot resolve; LLM: off gives template text).

## How to change

### Add a setting

1. Add the field to `Settings` in `apps/api/src/config/settings.py` with a default and a short comment.
2. Read it with `get_settings()` where needed. Do not define the value anywhere else.
3. Add a row to the Configuration tables in this file. Add it to `apps/api/.env.example` only if developers need it.
4. If deployment must set it, add it to `deploy/compose/` and `deploy/helm/agent-analytics/values.yaml` (see [deployment](../deployment/README.md)).

### Add a read route

1. Add a function in `apps/api/src/store/queries.py` (SQL stays in `store/`).
2. Add response models in `apps/api/src/models/api.py` (`snake_case`, `Label` where it applies, `Paged[T]` for growing lists).
3. Add `apps/api/src/routes/<name>.py` with `router = APIRouter(prefix="/<name>", tags=["<name>"])`. Use `ScopeDep` for screens with global filters and `Site` for single-record routes.
4. Add the module to `API_MODULES` in `apps/api/src/routes/__init__.py`.
5. Add a test in `apps/api/tests/api/` (empty case, filters, `404`/`422`). Add the route to `PROTECTED` in `tests/api/test_auth.py` only if it changes state.
6. Update the Routes table in this file and the screen doc in [dashboard](../dashboard/README.md).

### Add a filter to a list route

1. Add the query parameter (with a `pattern` for fixed values) in the route.
2. Pass it into `scope.filters(...)` or the `queries` call, and handle it in `queries.py`.
3. Add a case to the route test. Update the parameter list in the Routes table.

### Add an error code

Raise `error(status, "<code>", "<message>")` from `params.py`. Add the code to the table above and a test.

### Add a CLI command

1. Add `@app.command("<name>")` in `apps/api/src/cli.py`. Call a service function. Wrap DB work in `run_with_pool()`.
2. Use `typer.Exit(<code>)` for failures. Print errors with `err=True`.
3. Add a wiring test in `apps/api/tests/pipeline/test_cli.py`. Update the CLI table in this file and in `apps/api/README.md`.

### Add a log field

Pass it with `extra={...}` to the logger call. No formatter change is needed. Do not pass names that clash with `LogRecord` attributes.

### Change the auth rule

Edit `require_api_token` in `apps/api/src/routes/auth.py`. Update `tests/api/test_auth.py` and rules B1 to B4 here.

## Tests

| Path | Covers |
|---|---|
| `apps/api/tests/test_app.py` | `/livez`, `/metrics`. |
| `apps/api/tests/api/test_params.py` | Site default and unknown site, bad params `422`, `class` list, default range, paging, `/api/sites`. |
| `apps/api/tests/api/test_auth.py` | `API_TOKEN` guard on `/api`, open `/health` and `/ingest`. |
| `apps/api/tests/api/test_overview.py`, `test_recommendations.py`, `test_agents.py`, `test_events.py`, `test_sessions.py`, `test_pages_journeys_runs.py` | One file for each screen: filters, paging, detail, `404`. |
| `apps/api/tests/pipeline/test_health.py` | `/health`, `/livez`. |
| `apps/api/tests/pipeline/test_cli.py` | CLI commands and exit codes. |
| `apps/api/tests/ingest/test_ingest_route.py`, `test_imports_route.py`, `test_limits.py`, `test_quota.py` | `/ingest`, `/api/imports*`, rate limit, byte quota. |

Tests need Postgres on port 55432. Set `TEST_DATABASE_SERVER_URL` to use another server. See [testing](../testing/README.md).

```sh
cd apps/api
uv run pytest tests/api tests/test_app.py
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

## Related modules

- [pipeline](../pipeline/README.md): the worker loops, lanes, locks and `/health` inputs.
- [ingestion](../ingestion/README.md): what happens to a file after `/ingest`, upload or CLI import.
- [recommendations](../recommendations/README.md): the run that `POST /api/recommendations/generate` starts.
- [store](../store/README.md): `queries.py`, `quota.py`, `db.py`.
- [dashboard](../dashboard/README.md): UI URLs and screens that call these routes.
- [deployment](../deployment/README.md): how settings reach the containers, ingress rules for `/ingest` and `/api`.
- [testing](../testing/README.md): test setup and fixtures.
- [architecture](../architecture/README.md): system map and stack decisions.
