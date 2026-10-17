# Agent rules

## Repo

| Path | Content |
|---|---|
| `docs/` | Product and design docs. `docs/mvp-flows.md` = back-end flows (source of truth). `docs/on-prem.md` = on-prem infrastructure. |
| `apps/api/` | Back end: FastAPI API, worker, CLI. Python + uv. |
| `apps/dashboard/` | Next.js dashboard. |
| `deploy/` | On-prem: Docker Compose (dev, demo), Helm chart (production), Vector config. |

## Python (`apps/api`)

- Use the Python version in `apps/api/.python-version` (latest stable).
- Use uv for all commands: `uv sync`, `uv add`, `uv run`. Do not use pip.
- The project is not a package (`[tool.uv] package = false`). Do not change this. Code runs from `apps/api` as the top-level package `src` (`from src.config import get_settings`).
- Never use `from __future__ import annotations`. It is not required on Python 3.14+ (annotations are evaluated lazily). Ruff rule TID251 rejects it.
- Do not name a module or folder after a standard library module (for example `logging`, `types`, `queue`). The shared logger is `src/logger`.
- All Postgres and inbox access goes through `src/store` (decision S.3). Routes and services do not write SQL outside it.
- Database access: psycopg 3 and plain SQL. No ORM. Migrations: Alembic with `op.execute`.
- Checks before a commit: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
