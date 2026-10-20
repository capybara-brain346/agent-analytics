# src

Back-end code. Top-level package `src` (run from `apps/api`).

```
CDN / origin logs ──► routes/ingest ──► S3 inbox ──► services/pipeline (worker)
                                                          │ fast lane: import → pair → verify → classify → views
                                                          │ slow lane: recommendations
                                                          ▼
                                                     Postgres (store/)
                                                          │
dashboard ◄── routes/* (/api, read-only) ◄────────────────┘
```

| Path | Content |
|---|---|
| `main.py` | FastAPI app. Opens the DB pool. Mounts `routes`. |
| `cli.py` | Typer CLI: `worker`, `run-pipeline`, `run-recommendations`, `import`, `cleanup`, `download-ip-lists`. |
| `config/` | Settings from env. |
| `logger/` | JSON logging. |
| `models/` | Enums and API response models. No logic. |
| `routes/` | HTTP endpoints. |
| `services/` | Business logic, one folder per service. |
| `store/` | All SQL and S3 access. |

Back-end specs: `docs/modules/` (start at `docs/modules/README.md`).
