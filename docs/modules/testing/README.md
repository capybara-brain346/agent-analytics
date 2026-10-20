# Testing

This module covers the automated tests (pytest for the API, `node --test` for the dashboard), the synthetic sample logs in `samples/logs/`, and the real-site test on a live website.
Input: code, a test Postgres server, sample log files, a live site. Output: pass or fail, and a pipeline run to inspect by hand.

## Read this when

- You add or change a test, a fixture or a factory.
- You must run the checks before a commit.
- You need demo or test data: load `samples/logs/`.
- You add a sample log scenario or change the file name rule for log files.
- You run, change or extend the real-site test (`piyushc.com`): see [real-site-test.md](real-site-test.md).
- A test fails because Postgres is not reachable, or because a local site file changes the result.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/tests/conftest.py` | Shared fixtures: `db_url`, `settings`, `base_config_dir`, `config_dir`, `now`, `clean_db`, `conn`, `pool`, `client`. |
| `apps/api/tests/factories.py` | `make_*` row inserters (plain SQL) and constants `NOW`, `GPTBOT_UA`, `CHROME_UA`, `GPTBOT_IP`. |
| `apps/api/tests/fakes.py` | `MemoryInbox`: in-memory `Inbox` for ingest and e2e tests. |
| `apps/api/tests/foundation/` | Schema, partitions, dedupe index, factories, fixtures, registry, site config, keys, `import_files` store. |
| `apps/api/tests/importer/` | Importer, CDN and origin adapters, dedupe, delete, cleanup, bucket reader, local file. |
| `apps/api/tests/ingest/` | Ingest and imports routes, inbox limits, quota, S3 inbox (`fake_s3.py`). |
| `apps/api/tests/pairing/` | `test_pair_events.py`. |
| `apps/api/tests/verify/` | Verification and IP lists. |
| `apps/api/tests/classify/` | Rules, service, user-agent parsing. |
| `apps/api/tests/reconstruction/` | Views, sessions. |
| `apps/api/tests/recommendations/` | Patterns, generation. Has its own `conftest.py` and `helpers.py`. |
| `apps/api/tests/pipeline/` | Lanes, worker, CLI, health, alerts, retention, stale runs, store. |
| `apps/api/tests/api/` | HTTP route tests (agents, auth, events, overview, pages, journeys, runs, params, recommendations, sessions). Own `conftest.py` with a `traffic` fixture. |
| `apps/api/tests/e2e/` | `test_pipeline_e2e.py` (ingest to API), `test_delete_e2e.py` (import delete). Own `conftest.py` with an `inbox` fixture. |
| `apps/api/tests/test_app.py` | App smoke test. |
| `apps/api/pyproject.toml` | pytest config: `testpaths = ["tests"]`, `asyncio_mode = "auto"`, session-scoped event loops. |
| `apps/dashboard/src/lib/api/api.test.mjs` | Dashboard unit tests for `queryString`, `rangeOf`, `scopeFromQuery`, `scopeParams`. |
| `apps/dashboard/src/lib/log-name.test.mjs` | Dashboard unit test for `parseLogName`. |
| `samples/logs/` | 85 synthetic log files and `README.md` (file name rule, scenarios, load, delete). |
| `deploy/cloudflare-pages/` | Real-site capture: `README.md`, `capture.sh`, `site/piyushc.yaml`, `site/piyushc-pages.txt`. |
| `apps/api/config/sites/piyushc.yaml`, `piyushc-pages.txt` | Local copies of the `site/` files for a live run. Git ignores them (`.gitignore`: `apps/api/config/sites/piyushc*`). |
| `apps/api/config/cdn/cloudflare.yaml` | Field map for the capture lines. |

## Data flow

Automated tests:

```
 pytest session start
   │ create database aa_test_<random> on TEST_DATABASE_SERVER_URL
   │ alembic upgrade head
   ▼
 db_url ──► clean_db (TRUNCATE all tables, per test) ──► conn / pool ──► client (httpx on FastAPI app)
   ▲                                                            ▲
 base_config_dir (copy of apps/api/config, only site "example") │ factories.make_* (SQL rows)
   │ CONFIG_DIR                                                  │ fakes.MemoryInbox (inbox override)
   ▼                                                            │
 config_dir (per-test copy, tests may add site files) ──────────┘
   │
 pytest session end: DROP DATABASE aa_test_<random> WITH (force)
```

Sample logs:

```
 samples/logs/<site>__<source>__<start>[__<label>].log[.gz]
   │ dashboard drop (Data & pipeline > Sources)   or   cli import <path> --now
   ▼
 inbox ──► import_files ──► events ──► (run-pipeline fast) ──► sessions, pages, agents
   ▲
 Delete import (dashboard) removes the events and the file record
```

Real-site test: see the diagrams in [real-site-test.md](real-site-test.md).

## Rules and decisions

1. Tests need Postgres on port 55432. Each session makes and drops its own database.
   Why: tests do not touch the dev database and run in isolation.
2. Tests ignore `apps/api/.env`. Only process environment variables apply (`Settings.model_config["env_file"] = None` in `tests/conftest.py`).
   Why: a developer's `OFFLINE`, `API_TOKEN` or LLM keys must not change results.
3. Tests know one site: `example`. `base_config_dir` (session, autouse) copies `apps/api/config` and deletes every site file except `example.yaml`.
   Why: a local `piyushc*` file made 39 tests fail before this rule.
4. `conn` uses AUTOCOMMIT. Every statement commits at once. A test that needs a transaction writes `async with conn.transaction(): ...`.
   Why: other connections (pool, client) must see the data.
5. Database fixtures are lazy. A test that does not use `db_url`, `conn`, `pool` or `client` never opens Postgres.
   Why: pure unit tests run without a server.
6. Tests insert rows with `make_*` factories (plain SQL). Each factory takes column overrides and returns the row as a dict.
   Why: tests state only the columns that matter.
7. Default test scene: GPTBot (`GPTBOT_UA`) at `GPTBOT_IP` (`20.171.1.5`) fetches `/pricing` at `NOW` (`2026-10-17 12:00 UTC`), status 200.
8. Use `MemoryInbox` for ingest and e2e tests. Do not use real S3.
9. Test philosophy: write the minimum number of tests that protect meaningful behavior. The rules are in [`AGENTS.md`](../../../AGENTS.md), section "Testing Philosophy". Read them before you add tests. This file does not copy them.
10. The files in `samples/logs/` are synthetic and fictional. They show that the pipeline works. They are NOT evidence of real agent behavior. IP ranges are documentation, test or sample vendor ranges.
    Why: only the real-site test gives real agent traffic.
11. Sample data is test data, not database rows. Load the files you need, delete them when done, load them again later.
12. A log file name follows `<site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log[.gz]`. See "Sample logs" below.
    Why: a dropped file has no folder, so the site and the source travel in the name.
13. Never put capture files from the real-site test into `samples/` or a commit. They hold real visitor IP addresses.
14. Do not report a check as passing unless it completed. A test that needs Postgres fails when the server is down: say so.

## Configuration

| Setting | Default | Effect |
|---|---|---|
| `TEST_DATABASE_SERVER_URL` | `postgresql://agent_analytics:agent_analytics@localhost:55432/agent_analytics` | Postgres server for tests. The session creates `aa_test_<hex>` on it. |
| `DATABASE_URL` | set by `db_url` for the session | Points settings to the test database. `db_url` restores the old value at the end. |
| `CONFIG_DIR` | set by `base_config_dir` / `config_dir` | Points settings to a test copy of `apps/api/config`. |
| `OFFLINE`, `OPENROUTER_API_KEY` | set by `e2e/conftest.py` `inbox` fixture (`true`, empty) | e2e tests run without network and without an LLM key. |
| `RAW_RETENTION_DAYS` | `7` (`settings.py`: `raw_retention_days`) | Delete of a sample import is refused (`409`) when the paired raw file is gone. |
| `EVENTS_RETENTION_DAYS` | `30` (`settings.py`: `events_retention_days`) | Cleanup drops event partitions older than this. Old sample data is removed. |
| `CAPTURE_MINUTES` | `30` | Real-site capture time limit (`capture.sh`). |

## Interfaces

Fixtures (`tests/conftest.py`):

| Fixture | Scope | Gives |
|---|---|---|
| `db_url` | session | URL of a fresh migrated database. |
| `settings` | test | `Settings` object. Loads `db_url` first when the test uses it. |
| `base_config_dir` | session, autouse | Config copy with only `example`. |
| `config_dir` | test | Writable config copy, wired into `CONFIG_DIR`. |
| `now` | test | `NOW` from `tests/factories.py`. |
| `clean_db` | test | TRUNCATE of all tables except `alembic_version`. |
| `conn` | test | `AsyncConnection`, autocommit on. |
| `pool` | test | The `src.store.db` pool on the test database. |
| `client` | test | `httpx.AsyncClient` on `create_app()`, pool open. |

Factories (`tests/factories.py`), all `async def make_*(conn, **overrides) -> dict`:
`make_import_file`, `make_event`, `make_verdict(conn, *, classified=False, ...)`, `make_session(conn, *, open=False, ...)`, `make_session_event`, `make_page_stats`, `make_journey_step`, `make_agent`, `make_recommendation_run`, `make_recommendation`, `make_pipeline_run`, `make_site_work`, `make_alert`, `make_ip_list_snapshot`. Low-level: `insert_row(conn, table, values)`.

CLI for sample data (from `apps/api`, `uv run python -m src.cli ...`):

| Command | Use |
|---|---|
| `import <path> [--site S] [--source cdn\|origin] [--now] [--force]` | Import one file, or every `.log` and `.log.gz` file in a folder (name order). Without `--site` and `--source`, both come from the file name. Exit code 2: empty folder or no site. |
| `run-pipeline fast --site <site>` | Pair, verify, classify and build the views. |
| `run-recommendations --site <site>` | Run the slow lane. |

## Sample logs

Folder: `samples/logs/`. Full scenario table and expected results: `samples/logs/README.md`. That file is the source of truth for the scenarios.

| Item | Value |
|---|---|
| Site | `example` |
| Period | 2026-10-12 00:00Z to 2026-10-18 10:00Z |
| Files | 85 (one CDN file and one origin file per scenario and day, `<scenario>-d<DD>`; one extra `coverage-d16-resend`) |
| Size | about 18 MB compressed, about 1 million lines |
| Scenarios | `humans`, `crawlers`, `spoof`, `failures`, `coverage`, `edge` |

File name rule:

| Part | Value |
|---|---|
| `site` | Site ID from `apps/api/config/sites/`. Letters, digits, `-`, single `_`. |
| `source` | `cdn` or `origin`. Must be a source of that site. |
| `YYYYMMDDTHHMMZ` | UTC time of the first line. Sorts the files. The import uses the timestamp on each line. |
| `label` | Optional. What the file shows. |

A file whose name breaks the rule uses the site and source that the dashboard has selected.

Load:

```sh
# dashboard: Data & pipeline > Sources, drop files or Upload log files
cd apps/api
uv run python -m src.cli import ../../samples/logs --now
uv run python -m src.cli run-pipeline fast --site example
```

Delete: Data & pipeline > Imports > open file > **Delete import**. It removes the events and the file record. The next fast-lane run rebuilds the views. If the file has paired rows, the paired file of the other source is read again. After a delete you can load the same file again.

The delete returns `409` when:

- a pipeline run of the site is active,
- the file is still importing,
- a paired file cannot be read again because cleanup removed its raw file (after `RAW_RETENTION_DAYS`).

## Known limits

- Sample timestamps are fixed. Dashboard ranges count back from now, so old sample data falls out of the selected range.
- The cleanup job drops event partitions older than `EVENTS_RETENTION_DAYS` (30 days). Sample data older than that is removed at the next cleanup.
- Files of different scenarios cover the same hours, so the import list shows an overlap warning between them. Request IDs are unique, so no event is counted twice.
- Googlebot and bingbot need reverse DNS. Offline, they stay unverified.
- Origin lines with `\"` in a quoted field are rejected (nginx writes a quote as `\x22`). This is intended in the `edge` scenario.
- The dashboard has unit tests for `src/lib` only. There are no component or browser tests in the repository.
- The real-site test has its own limits: see [real-site-test.md](real-site-test.md).

## How to change

| Task | Steps |
|---|---|
| Add a test to an existing area | Add it in the matching `apps/api/tests/<area>/` folder. Use `make_*` factories and the `conn` or `client` fixture. Check existing coverage first (see `AGENTS.md`). |
| Add a factory for a new table | Add `make_<table>` in `tests/factories.py` with `insert_row`. Add the table to the JSON columns set when it has JSON columns. Add it to `test_all_factories_insert` in `tests/foundation/test_infra.py`. |
| Test with an extra site | Use `config_dir`. Write `config_dir / "sites" / "<id>.yaml"`. See `tests/ingest/conftest.py` (`solo` site). |
| Test ingest without S3 | Use `MemoryInbox` and override `inbox_dependency` (see `tests/e2e/conftest.py`). |
| Add a sample log scenario | Add files with the name rule to `samples/logs/`. Add a row to the scenario table in `samples/logs/README.md`. Use documentation or test IP ranges only. |
| Add a dashboard unit test | Add `*.test.mjs` next to the code. Add the path to the `test` script in `apps/dashboard/package.json`. |
| Change the log file name rule | Change `parse_log_name` in `apps/api/src/services/importer/log_names.py` and `parseLogName` in `apps/dashboard/src/lib/log-name.ts`. Update `samples/logs/README.md`. Run both test suites. |
| Add a second live site | Follow [real-site-test.md](real-site-test.md), section "How to change" (row "Add a site"). |

## Tests

Back end, from `apps/api` (needs Postgres on port 55432):

```sh
docker run -d --name aa-test-pg -p 55432:5432 \
  -e POSTGRES_USER=agent_analytics -e POSTGRES_PASSWORD=agent_analytics \
  -e POSTGRES_DB=agent_analytics postgres:17
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pytest
uv run pytest tests/classify          # one area
```

Dashboard, from `apps/dashboard`:

```sh
npm run lint && npm test && npm run build
```

`npm test` runs `node --experimental-strip-types --test` on the two `.test.mjs` files.

The best end-to-end check is `tests/e2e/test_pipeline_e2e.py`. It runs ingest, import, pair, verify, classify, views, recommendations and the API with a fake resolver and `MemoryInbox`.

## Related modules

- [Architecture](../architecture/README.md)
- [Ingestion](../ingestion/README.md)
- [Classification](../classification/README.md)
- [Pipeline](../pipeline/README.md)
- [Dashboard](../dashboard/README.md)
- [Deployment](../deployment/README.md)
