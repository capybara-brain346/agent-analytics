# Architecture

Whole-system view of Agent Analytics. It reads CDN and origin access logs. It finds AI agents and bots, verifies who they are, rebuilds what they did, and ranks the journeys to test next.
Input: access log files from the customer. Output: verified identities, sessions, journeys and ranked recommendations, shown in a dashboard.

## Read this when

- You must know which module owns a task.
- You must add a service, a process, a table or a technology.
- You must decide where code goes (`routes`, `services` or `store`).
- You must understand the two deployment targets (on-prem, managed).
- You must find the right file in the repo.

## Product purpose

- Question: can we turn observable AI-agent traffic into trustworthy evidence, and use it to decide which journeys to test next?
- Users: product managers (decide which agent journeys to test) and engineers (inspect evidence and data coverage).
- Every claim has one label: `Observed`, `Inferred` or `Unknown` (`EvidenceLabel` in `apps/api/src/models/domain.py`).
- An identity claim stays unverified until the verify step proves it.
- An HTTP 200 does not prove that an agent completed a task. Logs show "reached step N", never "done".
- Agents do not call our system. An agent calls the customer site, and the site writes a log line. Our system starts at the log file.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/` | Python 3.14 back end: FastAPI, psycopg 3, Alembic, Typer. One image runs `api`, `worker` and `migrate`. |
| `apps/api/src/main.py` | FastAPI app. Opens the DB pool. Warns when `API_TOKEN` is unset. Mounts `root_router` and `api_router` (prefix `/api`). |
| `apps/api/src/cli.py` | Typer CLI: `worker`, `run-pipeline`, `run-recommendations`, `import`, `cleanup`, `download-ip-lists`. |
| `apps/api/src/config/settings.py` | Every setting and default (environment variables). `get_settings()` is cached. |
| `apps/api/src/logger/` | JSON logging to stdout. `configure_logging(level)`, `get_logger(__name__)`. |
| `apps/api/src/models/` | `domain.py` (enums, `TrafficClass` 1-6), `api.py` (response models), `keys.py` (`client_key(ua, ip)`, `normalize_ip`). No logic, no I/O. |
| `apps/api/src/routes/` | HTTP endpoints. Thin: read params, call `store` or `services`, map to `models.api`. |
| `apps/api/src/services/` | Business logic. One folder per service, no SQL. |
| `apps/api/src/store/` | All Postgres and S3 (inbox) access. |
| `apps/api/config/` | YAML data: `cdn/` (field maps), `registry/` (bot registry, `ip-lists/`, `shared-ip.yaml`), `sites/` (one file per site). |
| `apps/api/migrations/versions/` | Alembic migrations in raw SQL (`0001_initial.py` to `0005_import_fixes2.py`). |
| `apps/api/tests/` | pytest: unit, API and end-to-end tests. |
| `apps/api/Dockerfile` | One image for `api`, `worker` and `migrate`. |
| `apps/dashboard/` | Next.js dashboard. Calls the API through the same-origin proxy `apps/dashboard/src/app/dashboard-api/`. |
| `deploy/compose/` | Docker Compose stack for dev and demo. |
| `deploy/helm/agent-analytics/` | Helm chart for production. |
| `deploy/vector/vector.toml` | Origin log sender config for the customer. |
| `deploy/dashboard/Dockerfile` | Dashboard image. |
| `deploy/cloudflare-pages/` | Live-site test capture (a Pages site as a log source). |
| `samples/logs/` | Fictional CDN and origin logs. Test and demo data only. |
| `docs/modules/` | One folder per module (this documentation). |

### Service folders in `apps/api/src/services/`

Each folder has `service.py` plus private helpers. `__init__.py` exports the public API:

```python
from src.services import importer

await importer.import_due_files(conn, site_id)
```

| Folder | Role | Module doc |
|---|---|---|
| `importer/` | Read inbox files, parse, validate, dedupe, write `events`. Bucket reader. | [ingestion](../ingestion/README.md) |
| `ingest/` | Push upload `POST /ingest`: checks and write to the inbox. | [ingestion](../ingestion/README.md) |
| `pairing/` | Join CDN and origin lines of one request. | [pairing](../pairing/README.md) |
| `verify/` | Check a claimed identity (IP list, rDNS). | [verification](../verification/README.md) |
| `registry/` | Load the bot registry YAML. | [verification](../verification/README.md), [classification](../classification/README.md) |
| `classify/` | Assign one of 6 traffic classes. | [classification](../classification/README.md) |
| `reconstruction/` | Build sessions and hourly views. | [activity-reconstruction](../activity-reconstruction/README.md) |
| `recommendations/` | Patterns P1-P5, score, fact bundle, LLM text. | [recommendations](../recommendations/README.md) |
| `pipeline/` | Run lanes per site, locks, worker loops, retention. | [pipeline](../pipeline/README.md) |
| `alerts/`, `cleanup/` | Alerts, deletion of expired raw files and event partitions. | [pipeline](../pipeline/README.md) |
| `site_config/` | Load `config/sites/<site_id>.yaml`. The site list is the file list. | [pipeline](../pipeline/README.md) |

`services/labels/` is an empty folder. Do not add code there without a decision.

## Data flow

### System

```
  CUSTOMER SIDE                         AGENT ANALYTICS
 +----------------------+  gzip chunks  +--------------------------------------------------------+
 | CDN log push --------+------+        |                                                        |
 | nginx -> Vector -----+------+------->| api  POST /ingest --stream--> Inbox (S3 API)           |
 | CDN bucket <-- read -+--+   | token,  |      (202, no parsing)            |                    |
 +----------------------+  |   | quota   |                                   | import_files       |
   PM: upload, CLI -------+--+---+        |                                   v (= the queue)      |
                          +------------->| worker - FAST LANE (1 min) ----------------------+    |
                                         |          import>pair>verify>classify>views       |    |
                                         |        - SLOW LANE (6 h / on demand) -------+    |    |
                                         |          recommendations -> LLM text (opt.) |    |    |
                                         |                                             v    v    |
                                         |                                      PostgreSQL 17     |
                                         |                                             |          |
                                         | api  GET /api/* (read only) <---------------+          |
                                         +----------------+---------------------------------------+
                                                          v
                                  dashboard (Next.js) -- same-origin proxy -- PM / engineer / agent
```

### End-to-end pipeline map

```
 raw log line
   |  [ingestion]               adapter + CDN field map, validate, dedupe
   v
 events (one provider-neutral table, daily partitions)
   |  [pairing]                 edge_request_id + method + path, +/- 5 s
   v
 events (source = paired | cdn | origin)
   |  [verification]            client_key = (User-Agent, IP): one check per client
   v
 verdicts (VERIFIED | CLAIMED | UNVERIFIED | SPOOFED | UNKNOWN), append-only
   |  [classification]          first matching rule wins, rule_version stored
   v
 verdicts with traffic_class 1-6
   |  [activity-reconstruction] client -> session -> pages, retries, loops, gaps
   v
 open_sessions, sessions, session_events, page_stats, journey_steps, agents
   |  [recommendations]         5 pattern queries, score, fact bundle, text
   v
 recommendation_runs, recommendations (append-only, ranked)
   |
   v
 [api] GET /api/*  ->  [dashboard]
```

Fast lane steps (`FAST_STEPS` in `apps/api/src/services/pipeline/service.py`): `import`, `pair`, `verify`, `classify`, `views`. Each step has the signature `(conn, site_id) -> counts dict`.

| Lane | Steps | Trigger | Default interval |
|---|---|---|---|
| Fast (`Lane.FAST`) | import, pair, verify, classify, views | Worker tick, or `run-pipeline fast --site S` | `TICK_SECONDS` = 60 |
| Slow (`Lane.SLOW`) | recommendations | Worker tick, "Generate now", or `run-pipeline slow --site S` | One run for each `RECOMMENDATION_WINDOW` (6 h) |

### Ingest to dashboard (sequence)

```
 Sender        api (/ingest)       Inbox (S3)     Postgres        worker          dashboard
   | POST chunk     |                  |             |               |               |
   |--------------->| check token,     |             |               |               |
   |                | rate, quota      |             |               |               |
   |                |--stream parts--->|             |               |               |
   |                | INSERT import_files (status new) ------------->|               |
   |<---202---------|                  |             |               |               |
   |                |                  |             |<--tick: due?--|               |
   |                |                  |<--read file-+---------------|               |
   |                |                  |             |<--steps 1..5--|               |
   |                |                  |             |  (1 txn each) |               |
   |                |                  |             |               |               |
   |                |<--------GET /api/* (token, site, time scope)-----------------------|
   |                |---------------JSON (read only)---------------------------------->|
```

## Process roles

One image (`apps/api/Dockerfile`) runs three processes. The command picks the role.

| Process | Command | Role |
|---|---|---|
| `api` | `uvicorn src.main:app` | `POST /ingest` (writes the inbox only). `GET /api/*` (read only, plus 3 state changes). `/health`, `/livez`, `/metrics`. |
| `worker` | `python -m src.cli worker [--lanes fast\|slow\|all]` | Loops that run the fast and slow lanes. Reads CDN buckets. Daily maintenance. |
| `migrate` | `alembic upgrade head` | One-shot. Applies migrations, then exits. |
| `dashboard` | Next.js server (`deploy/dashboard/Dockerfile`) | UI. Proxies `/dashboard-api` to the API. Keeps the API token on the server. |

Other services in the stack: PostgreSQL 17, S3-compatible storage (inbox), and an ingress (Caddy in Compose, the customer's controller in Kubernetes).

Details: [pipeline](../pipeline/README.md) (worker, locks), [api](../api/README.md) (routes), [deployment](../deployment/README.md) (images, Compose, Helm).

## Deployment targets

| | On-prem | Managed |
|---|---|---|
| Tenancy | One customer, one network | Many customers, one shared system |
| Pipeline | Same | Same |
| Images | Same | Same |
| Isolation key | `site_id` | `site_id` |
| Status | Compose (dev, demo), Helm (production) | Infrastructure not written yet |

- Every data table has a `site_id` column and `site_id` leads its indexes and primary keys.
- Exception: `ip_list_snapshots` has no `site_id`. It holds vendor IP lists, shared by all sites.
- A site exists when `apps/api/config/sites/<site_id>.yaml` exists. `site_config.list_sites()` returns the list.
- The ingest token of a site is stored in its YAML as `ingest_token_sha256`.
- `/api/*` takes one `API_TOKEN` for all sites. It has no per-tenant access control yet (see Known limits).

## The 6 traffic classes

`TrafficClass` in `apps/api/src/models/domain.py`. First matching rule wins. Rules: [classification](../classification/README.md).

| # | Name | One line |
|---|---|---|
| 1 | `VERIFIED_SEARCH_CRAWLER` | Search crawler whose identity the verify step confirmed. |
| 2 | `KNOWN_AI_CRAWLER` | AI crawler or agent client from the bot registry. Confidence follows the verify verdict. |
| 3 | `OTHER_IDENTIFIABLE_BOT` | Other bot or library User-Agent, or a search crawler that is not verified. |
| 4 | `BROWSER_AUTOMATION` | Headless User-Agent, or the edge says bot with a browser User-Agent. |
| 5 | `ORDINARY_BROWSER` | Browser User-Agent and the edge says human. |
| 6 | `UNKNOWN` | Everything else, and every `SPOOFED` client. |

## Rules and decisions

Technology rules. Each rule is a decision that other modules assume.

| ID | Rule | Why |
|---|---|---|
| A1 | One PostgreSQL holds all data. No second log database. [S.1] | Steps need transactions across `events`, `verdicts` and `import_files`. One service fewer in a bank network. |
| A2 | Use psycopg 3 and plain SQL. No ORM. Alembic migrations are raw SQL (`op.execute`). | The pipeline needs window functions and bulk `COPY`. An ORM hides both. |
| A3 | Only `apps/api/src/store/` holds SQL and S3 access. [S.3] | A move to another store later changes one module. |
| A4 | `services/` has no SQL. `routes/` stay thin. | One place for each kind of change. |
| A5 | The `import_files` table is the work queue. No Kafka, RabbitMQ or SQS. [7.8] | `FOR UPDATE SKIP LOCKED` gives safe parallel work and crash retry. No second list to keep in agreement. |
| A6 | The scheduler is a loop inside the worker. No cron, no extra service. [7.1] | One service fewer. No container start delay at a 1-minute tick. |
| A7 | One Postgres advisory lock for each site + lane. [7.2] | Sites run in parallel. One site never runs twice at once. |
| A8 | The customer pushes logs. We never fetch from customer hosts. [1.14] | No credentials into customer hosts. Vector buffers on disk while we are down. |
| A9 | Logs are the only collection path (CDN + origin). Pair them by default. [1b.1] | Logs see crawlers that do not run JavaScript. Pairing shows edge blocks and origin failures for one request. |
| A9b | Three entry points put a file in one inbox, and one parser reads it: automatic log delivery (main), dashboard upload, CLI. [1.1] | One parser, one set of rules for all sources. |
| A10 | Use micro-batches, not a per-line stream. [1.13] | CDN push sets a 30 s to 5 min floor anyway. A stream needs a broker and exactly-once logic. |
| A11 | The `events` schema is provider-neutral. CDN differences live in YAML field maps only. [1b.4] | A new CDN is a data change, not a code change. |
| A12 | The bot registry is data (YAML). Rule order stays in code, with `rule_version`. [2.10, 3.3] | A new bot is a YAML edit. |
| A13 | Verify by IP list first, then rDNS. A DNS error is `UNVERIFIED`, not `SPOOFED`. [2.4, 2.6] | A User-Agent is a claim. A failed check is not proof of a lie. |
| A14 | Verdicts and recommendation runs are append-only. [2.8, 5.4] | Auditability. Monday's verdict stays true for Monday's events. |
| A15 | A browser User-Agent without an edge signal is class 6 `UNKNOWN`. [3.6] | A User-Agent is a claim. Do not assume human. |
| A16 | Views are incremental: open sessions, closed sessions, hourly rows. [4.1] | Cost grows with active visits, not with history. |
| A17 | Rules find patterns. The LLM only writes text. A validator checks the text. Template text is the fallback. [5.7, 5.8] | Facts cannot be invented. Banks may block outside calls. |
| A18 | Config (sites, registry, CDN maps, thresholds) lives in files and `settings.py`, not in the UI. | Reviewable, versioned, same for both targets. |
| A19 | Database sessions use time zone UTC. | One time base for all sites. |
| A20 | Use the customer's S3-compatible storage for the inbox. SeaweedFS (Apache-2.0) if there is none. | One S3 API in the code. Banks often have storage already. |
| A21 | Use Kubernetes + Helm for production. Use Compose for dev, demo and trial only. | Kubernetes keeps running when one machine fails and updates without outage. Compose has no backups and no failover. |
| A22 | The customer's own tools read `/metrics` (Prometheus), `/health` and JSON logs on stdout. | Fits what the customer already runs. |

IDs in brackets (for example `[S.1]`, `[7.8]`) are the decision IDs of the module that owns the decision. See the related modules.

## Technologies

| Layer | Technology | Why |
|---|---|---|
| Language, packages | Python 3.14 + uv (`package = false`, one lock file in `apps/api`) | Fast, reproducible installs. Code runs from `apps/api` as top-level package `src`. |
| API | FastAPI + uvicorn | Async. Streamed uploads keep memory flat. |
| Database access | psycopg 3 (pool), plain SQL | See A2. |
| Migrations | Alembic (raw SQL) | Standard. Handles table partitions. |
| CLI | Typer | Manual runs, demo, tests. |
| Dashboard | Next.js 16, React 19, TypeScript, shadcn/ui | UI stack for `apps/dashboard`. |
| Database | PostgreSQL 17 | Relational data, transactions across steps. One database (A1). |
| Database high availability | CloudNativePG (Kubernetes operator) | Primary + standby, automatic failover, backups, point-in-time restore. We do not write this. |
| File storage (inbox) | S3-compatible storage (boto3) | See A20. Examples of customer storage: NetApp StorageGRID, Dell ECS, Ceph. |
| Production runtime | Kubernetes + Helm chart | See A21. Banks already run it (or OpenShift). |
| Dev and demo runtime | Docker Compose, one machine | Simple local development. Same images as production. |
| Work queue | `import_files` table | See A5. |
| Scheduler | Loop in the worker container | See A6. |
| Locks | Postgres advisory lock for each site + lane | See A7. |
| Log delivery (origin) | Vector agent, installed by the customer | Free (MPL-2.0). One binary. Keeps data on disk while we are down. |
| Log delivery (CDN) | Vendor log push | Built into the CDN. Provider-neutral. |
| Upload | Streamed `POST /ingest` | The only method that Vector and CDN push support. |
| Entry and TLS | The customer's ingress or Gateway API controller. Caddy in Compose. | Banks use their own standard controller. |
| Secrets | Kubernetes Secret, or the customer's Vault through External Secrets. `.env` in Compose. | Fits what the customer already runs. |
| Monitoring | `/metrics`, `/health`, JSON logs to stdout | See A22. |
| Backups | CloudNativePG to S3, point-in-time restore | Built into the operator. |
| LLM (recommendation text) | OpenRouter, or a compatible gateway through `LLM_BASE_URL`, with the customer's key and `LLM_MODEL`. Or off (template text). | Banks may block outside calls. Template fallback exists. |
| Internet access | `OFFLINE=true`: IP lists and bot registry come from the release | Banks often block outside calls. |

### Not used

| Not used | Why not |
|---|---|
| MinIO | The free community edition is in maintenance mode (late 2025). License and support risk for banks. |
| Kafka, RabbitMQ, SQS | The Postgres table does the job (A5). |
| Our own ingress controller | Banks have their own. ingress-nginx was retired in 2026. |
| ClickHouse | Only above about 1 billion events/day. [S.5] |
| ORM | Hides the SQL that the pipeline depends on (A2). |

Note: `sqlalchemy` is in `apps/api/pyproject.toml` because Alembic needs it. The code in `src/` does not use an ORM.

## Configuration

Settings that define the shape of the system. All settings: `apps/api/src/config/settings.py`. Module settings: see each module doc.

| Setting | Default | Effect |
|---|---|---|
| `DATABASE_URL` | `postgresql://agent_analytics:agent_analytics@localhost:5432/agent_analytics` | The one PostgreSQL. |
| `DB_POOL_MAX_SIZE` | `10` | Pool cap, to fit the database connection limit. |
| `S3_ENDPOINT_URL` | `None` (AWS S3) | S3-compatible endpoint of the inbox. |
| `S3_BUCKET` | `agent-analytics-inbox` | Inbox bucket. |
| `TICK_SECONDS` | `60` | Worker loop period. |
| `RECOMMENDATION_WINDOW` | `6h` | Window of a recommendation run. Also the slow-lane interval (`6h`, `14d`). |
| `API_TOKEN` | `None` | Bearer token for `/api/*`. Unset = open, warning at start. |
| `OFFLINE` | `False` | No outside calls: no IP list download. |
| `OPENROUTER_API_KEY`, `LLM_MODEL` | `None` | Both needed for LLM text. Else template text. |
| `CONFIG_DIR` | `apps/api/config` | Root of the YAML data. |
| `LOG_LEVEL` | `INFO` | Log level. |

## Interfaces

| Interface | Detail |
|---|---|
| `POST /ingest?site=<site_id>` | Push upload, site token. Writes the inbox only. |
| `GET /api/*` | Read API for the dashboard. Bearer `API_TOKEN`. |
| `POST /api/imports/upload`, `DELETE /api/imports/{id}`, `POST /api/recommendations` | The only `/api` calls that change state. |
| `GET /health`, `GET /livez`, `GET /metrics` | Health (last success for each site + lane, unhealthy after `HEALTH_STALE_MINUTES` = 15), liveness, Prometheus. No auth. |
| `uv run python -m src.cli <command>` | `worker`, `run-pipeline fast\|slow --site S`, `run-recommendations --site S [--window 6h]`, `import PATH [--site S] [--now] [--force] [--source cdn\|origin]`, `cleanup`, `download-ip-lists`. |
| `pipeline.run_lane(site, lane)` | Run one lane for one site. Returns `RunResult`, or `None` when the lock is taken. |
| `pipeline.FAST_STEPS` | Ordered fast-lane steps. |
| Service step signature | `(conn: AsyncConnection, site_id: str) -> dict` (counts). |

## Known limits

| Limit | Detail |
|---|---|
| Task completion | A 200 is not success. Logs show "reached step N", never "done". |
| Undeclared bots with a browser UA | No UA claim and no edge signal: class 6 `UNKNOWN`. |
| Bots with no published IP list or rDNS | Stay `CLAIMED`. |
| Same IP is not same agent | Sessions are inferred. Shared IPs lower confidence. |
| Old events and new IP lists | Verify uses the latest snapshot. Its date is in the evidence. |
| Multi-tenant access control | One `API_TOKEN` covers all sites. Add SSO and roles before a managed target. |
| Sensitive data | Raw IPs and full URLs with query strings are stored. Add IP hashing or masking and query-string stripping before customer data. |
| Ingest rate limit | Per API process, in memory. With N replicas, the real limit is up to N times the setting. |
| HTTP message signatures (RFC 9421) | Not checked. Add when agents send signature headers. |
| Compose | No backups, no failover. Dev, demo and trial only. |
| Managed target | Infrastructure not written. Only the data model (`site_id`) and images are ready. |

Detail for each limit: [ingestion](../ingestion/README.md), [verification](../verification/README.md), [api](../api/README.md).

## Open questions

- Managed (multi-tenant) infrastructure: not designed.
- Helm chart: minimum Kubernetes version, and OpenShift support (security context rules).
- Path to production, in priority order: (1) redaction at import; (2) SSO and role-based access; (3) tune thresholds and the pairing window on real customer traffic; (4) match each event to the IP-list snapshot of its own date; (5) managed deployment; (6) scale path on measured need only (bigger Postgres, TimescaleDB compression, ClickHouse for events [S.5]).

## How to change

| Change | Where | Check |
|---|---|---|
| Add a bot | `apps/api/config/registry/bots.yaml` ([verification](../verification/README.md)) | `uv run pytest tests/classify tests/verify tests/foundation` |
| Add a CDN | New `apps/api/config/cdn/<vendor>.yaml`, set `cdn_field_map` in the site YAML ([ingestion](../ingestion/README.md)) | `uv run pytest tests/importer` |
| Add a site | New `apps/api/config/sites/<site_id>.yaml` with `ingest_token_sha256` | `uv run pytest tests/foundation` |
| Add a pipeline step | New folder in `apps/api/src/services/`. Add the step to `FAST_STEPS` in `apps/api/src/services/pipeline/service.py`. Put SQL in `apps/api/src/store/`. Add a migration if the schema changes. | `uv run pytest tests/pipeline tests/e2e` |
| Add a setting | `apps/api/src/config/settings.py` only. Import it where needed. Update the module doc. | `uv run pytest` |
| Add an API endpoint | New module in `apps/api/src/routes/`. Add it to `API_MODULES` in `apps/api/src/routes/__init__.py`. | `uv run pytest tests/api` |
| Change the schema | New file in `apps/api/migrations/versions/` (raw SQL). Keep `site_id` on every tenant table. | `uv run alembic upgrade head`, `uv run pytest` |
| Add a technology | Explain why and ask first (`AGENTS.md`, Architecture Boundaries). Update the Technologies table. | n/a |

## Tests

Run from `apps/api`. Tests need Postgres on port 55432 and ignore `apps/api/.env` ([testing](../testing/README.md)).

```sh
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

| Folder | Covers |
|---|---|
| `apps/api/tests/e2e/` | Full path: ingest, import, pair, verify, classify, views, recommendations, API. |
| `apps/api/tests/foundation/` | Store, keys, registry, site config, infrastructure. |
| `apps/api/tests/test_app.py` | App start. |

Each test session creates its own database and removes it at the end.

## Related modules

- [ingestion](../ingestion/README.md)
- [pairing](../pairing/README.md)
- [verification](../verification/README.md)
- [classification](../classification/README.md)
- [activity-reconstruction](../activity-reconstruction/README.md)
- [recommendations](../recommendations/README.md)
- [pipeline](../pipeline/README.md)
- [store](../store/README.md)
- [api](../api/README.md)
- [dashboard](../dashboard/README.md)
- [deployment](../deployment/README.md)
- [testing](../testing/README.md)
