# AGENTS.md

## Scope

These instructions apply to this repository. More specific `AGENTS.md` files in subdirectories override them.

Before changing a component, read the relevant package/config files and the applicable service or module documentation for that component.

Code and documentation changes should be scoped to the user’s request. Do not expand the architecture, introduce new systems, or make opportunistic refactors unless explicitly requested.

## Repository Map

- `apps/api/` — Python 3.14 back end (FastAPI, psycopg 3, Alembic, Typer). One image runs `api`, `worker` and `migrate`. See `apps/api/README.md`.
- `apps/api/src/services/` — one folder per pipeline step: importer, pairing, verify, classify, reconstruction, recommendations, pipeline. No SQL here.
- `apps/api/src/store/` — all Postgres and S3 (inbox) access.
- `apps/api/src/config/settings.py` — every configurable value and default (environment variables).
- `apps/api/config/` — YAML data: bot registry, IP lists, CDN field maps, site configs. A new bot or CDN is a data change, not a code change.
- `apps/api/migrations/` — Alembic migrations in raw SQL.
- `apps/api/tests/` — pytest: unit, API and end-to-end tests.
- `apps/dashboard/` — Next.js dashboard. Calls the API through the same-origin proxy `/dashboard-api`. See `apps/dashboard/README.md` and `apps/dashboard/AGENTS.md`.
- `deploy/` — Docker Compose (dev and demo), Helm chart (production), Vector sender config, live-site test capture for Cloudflare Pages (`deploy/cloudflare-pages/README.md`).
- `samples/logs/` — fictional CDN and origin log files, the test and demo data. See `samples/logs/README.md`.
- `docs/` — `mvp-flows.md` (flows and decisions, source of truth), `dashboard.md` (screens), `on-prem.md` (infrastructure), `task.pdf` (assignment brief).

## Commands

Back end, from `apps/api`:

- `uv sync` — install dependencies.
- `uv run ruff check . && uv run ruff format --check . && uv run pytest` — all checks before a commit. Tests need Postgres on port 55432 (`apps/api/README.md`) and ignore `apps/api/.env`.
- `uv run pytest tests/<folder>` — one test area, for example `tests/classify`.
- `uv run alembic upgrade head` — apply migrations. New migration: add a file in `migrations/versions/`.
- `uv run uvicorn src.main:app --reload` — run the API on port 8000.
- `uv run python -m src.cli import ../../samples/logs --now` — load the sample logs.
- `uv run python -m src.cli run-pipeline fast --site example` — run the fast lane now. `run-recommendations --site example` runs the slow lane.

Dashboard, from `apps/dashboard`:

- `npm run lint && npm test && npm run build` — all checks before a commit.
- `npm run dev` — run on http://localhost:3000 (needs the API on `API_URL`).

Full stack, from `deploy/compose`:

- `cp .env.example .env && docker compose up --build` — all services on https://localhost.

Do not report a command as passing unless it actually completed successfully. If a command is known to be unavailable, flaky, environment-dependent, or currently empty, state that clearly.

## Ponytail

Use the `ponytail` skill at its default `full` level for implementation, fixes, refactors, and reviews. Prefer the smallest correct change and do not add speculative abstractions or dependencies.

## Configuration

Define every configurable variable, constant, and default value inside the codebases' config file. Import these values where needed. Do not define configurable values elsewhere in the codebase.

## Code Spacing

Use consistent blank lines to make code easy to read. Put one blank line between functions and between groups of statements that do different tasks. Keep related statements together. Avoid large blocks with no blank lines, inconsistent spacing, and repeated blank lines.

## Python Guidelines

Never use `from __future__ import annotations`. It is not required on Python 3.14+ (annotations are evaluated lazily). Ruff rule TID251 rejects it.

## File Organization

When you write or change code, prefer focused files to one long file.

- Keep code concise and readable. Do not compress code or remove useful spacing to reduce the line count.
- Split files by purpose before they grow to hundreds of lines, such as 500 LOC. Use clear responsibilities to select file boundaries.


## Testing Philosophy

Write the minimum number of tests needed to protect meaningful behavior and prevent realistic regressions. Before adding tests, inspect existing coverage and avoid duplication. Prioritize observable behavior, critical paths, important edge cases, and regression tests for bugs. Do not test trivial logic, implementation details, framework behavior, or every possible input variation. Avoid excessive mocking, exhaustive test matrices, and tests written solely to increase coverage. Keep testing effort proportional to the risk and complexity of the change. Every new test should catch a distinct potential failure; stop adding tests once meaningful risks are covered. Small, low-risk changes do not automatically require new tests. Never remove valuable existing tests merely to reduce test count.

## Architecture Boundaries

Do not introduce new architecture without explicitly explaining why and asking first. Implement only the architecture requested.

## Documentation

Update the applicable README, service guide, or module documentation in the same change when modifying behavior, APIs, lifecycle, configuration, operations, or structure.

Keep durable architecture notes, workflows, and project-specific conventions in the appropriate documentation instead of growing this file unnecessarily.

## Commits

Commit messages must be specific, detailed, and production-level.

Use a precise Conventional Commit subject. Add a body when the change needs context, including the intent, affected behavior or scope, important implementation decisions, and verification.

Avoid generic messages such as `update docs`, `fix stuff`, or `misc changes`.
