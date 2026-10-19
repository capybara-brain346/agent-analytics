# Agent Analytics API

Back end for the flows in [docs/mvp-flows.md](../../docs/mvp-flows.md). On-prem deployment: [docs/on-prem.md](../../docs/on-prem.md).

One image, three commands:

| Process | Command |
|---|---|
| api | `uvicorn src.main:app` |
| worker | `python -m src.cli worker` |
| migrate | `alembic upgrade head` |

## Local development

```sh
cd apps/api
uv sync
cp .env.example .env
docker compose -f ../../deploy/compose/docker-compose.yml up -d postgres seaweedfs
uv run alembic upgrade head
uv run uvicorn src.main:app --reload
uv run python -m src.cli --help
```

## Tests

Tests need a Postgres server on port 55432. Each test session makes its own database and removes it at the end.

```sh
docker run -d --name aa-test-pg -p 55432:5432 \
  -e POSTGRES_USER=agent_analytics -e POSTGRES_PASSWORD=agent_analytics \
  -e POSTGRES_DB=agent_analytics postgres:17
uv run pytest -q
```

Use another server: set `TEST_DATABASE_SERVER_URL`. Tests ignore `apps/api/.env`: only process environment variables apply.

Checks before a commit: `uv run ruff check . && uv run ruff format --check . && uv run pytest`

`tests/e2e/test_pipeline_e2e.py` runs the full path: ingest, import, pair, verify, classify, views, recommendations, API.

## CLI

Run with `uv run python -m src.cli <command>`.

| Command | Use |
|---|---|
| `worker` | Run the worker loop (see below). |
| `run-pipeline fast\|slow --site S` | Run one lane for one site now. |
| `run-recommendations --site S [--window 6h]` | Make a recommendation run now. |
| `import PATH [--site S] [--now] [--force] [--source cdn\|origin]` | Import a log file, or every log file in a folder (name order). Without `--site` / `--source`, they come from the file name (`samples/logs/README.md`). |
| `cleanup` | Delete expired raw files and drop old event partitions. |
| `download-ip-lists` | Download vendor IP lists (offline mode: load the bundled files). |

## Worker

`python -m src.cli worker [--lanes fast|slow|all]` runs one loop for each lane group. A loop ticks every `TICK_SECONDS`. The loops are separate asyncio tasks with their own connections, so a slow recommendation run (LLM calls) does not delay the fast tick. With `--lanes fast` or `--lanes slow` one process runs one loop only (use two Deployments to scale them apart).

Fast loop, each tick:

1. Closes runs that a crashed worker left in status `running`.
2. Reads CDN buckets (only if `BUCKET_READER_ENABLED=true`, every `BUCKET_READER_INTERVAL_SECONDS`).
3. Runs the fast lane (import, pair, verify, classify, views) for each site that is due.

Slow loop, each tick: runs the slow lane (recommendations) for each site that is due. If the lock is taken (for example "Generate now" runs), the site is tried again after 5 minutes, not after a full window. Once each day this loop also downloads IP lists (not in offline mode), runs cleanup and prunes derived tables (hourly rows, sessions, `pipeline_runs`, `import_rejects`) older than `EVENTS_RETENTION_DAYS`. Recommendation runs are kept.

A site and lane run only once at a time (advisory lock).

## Layout

```
src/
  main.py      FastAPI app
  cli.py       Typer commands (see CLI)
  config/      settings from environment variables
  logger/      shared JSON logger (stdout)
  routes/      HTTP: /ingest, /health, /livez, /metrics, /api/*
  services/    flow logic, one subfolder for each service (<name>/service.py + related files)
  store/       all Postgres and inbox (S3) access (decision S.3)
  models/      fixed names (enums) and API response models
config/        YAML data: CDN field maps, bot registry, site configs
migrations/    Alembic, raw SQL
```

## Security and limits

- `/api/*` needs `Authorization: Bearer <API_TOKEN>` when `API_TOKEN` is set (constant-time compare). If it is not set, `/api/*` is open and the API logs a warning at start: set it in every shared environment, or expose only `/ingest` at the ingress. `/ingest` uses per-site tokens. `/health`, `/livez`, `/metrics` are open.
- `/ingest` byte quota (`INGEST_BYTES_PER_DAY`) is read from Postgres (sum of `import_files.size_bytes` of the last 24 h), so all API replicas share it.
- `/ingest` request rate (`INGEST_RATE_PER_MINUTE`) is a sliding window in process memory. With N API replicas the real limit is up to N times the setting.
- Database sessions use time zone UTC.
