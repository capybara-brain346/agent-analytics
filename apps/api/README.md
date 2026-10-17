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

Checks: `uv run ruff check . && uv run ruff format --check . && uv run pytest`

## Layout

```
src/
  main.py      FastAPI app
  cli.py       Typer commands: worker, run-pipeline, run-recommendations, import, cleanup
  config/      settings from environment variables
  logger/      shared JSON logger (stdout)
  routes/      HTTP: /ingest, /health, /livez, /metrics, /api/*
  services/    flow logic, one module for each flow step
  store/       all Postgres and inbox (S3) access (decision S.3)
  models/      fixed names (enums) and API response models
config/        YAML data: CDN field maps, bot registry, site configs
migrations/    Alembic, raw SQL
```

Status: scaffold. Routes return 501 and services raise `NotImplementedError` until each flow is built. The database schema is not written yet.
