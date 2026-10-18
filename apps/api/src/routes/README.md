# routes

FastAPI routers. Thin: read params, call `store` / `services`, map to `models.api`.

| Mount | Auth | Modules |
|---|---|---|
| `/` | none | `health` (`/livez`, `/health`), `metrics` (Prometheus), `ingest` (site token) |
| `/api` | `API_TOKEN` bearer (`auth.py`), open if unset | `overview`, `recommendations`, `agents`, `events`, `sessions`, `pages`, `journeys`, `imports`, `runs` |

- `params.py`: shared dependencies: DB connection, site, time scope, paging.
- `ingest` writes to the S3 inbox only. The worker imports the files later.
- Only `POST /api/imports` and `POST /api/recommendations` change state in `/api`.
