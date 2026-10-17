# On-prem infrastructure

Self-hosted inside one customer network. Same container images as the managed (AWS) target. Managed infrastructure: not written yet.

Flows, store design, locks and workers: [mvp-flows.md](mvp-flows.md).

## Status

| Part | Status |
|---|---|
| Technology choices | AGREED 2026-10-17 |
| Production runtime (Kubernetes + Helm) | AGREED 2026-10-17 |
| Dev and demo runtime (Docker Compose) | AGREED 2026-10-17 |
| Offline mode | PROPOSED 2026-10-17 |

---

## Files in the repo

| Path | Content |
|---|---|
| `apps/api/Dockerfile` | One image for `api`, `worker` and `migrate` |
| `deploy/compose/` | `docker-compose.yml`, `Caddyfile`, SeaweedFS S3 keys, `.env.example` |
| `deploy/helm/agent-analytics/` | Helm chart: api, worker, dashboard, migrate Job, CloudNativePG `Cluster`, `Ingress`, `HTTPRoute` |
| `deploy/dashboard/Dockerfile` | Dashboard image (build context `apps/dashboard`) |
| `deploy/vector/vector.toml` | Origin log sender config for the customer |

---

## Technologies and why

| Layer | Technology | Why |
|---|---|---|
| Language and packages | Python 3.14 + uv (`package = false`, one lock file in `apps/api`) | Team choice. Fast, reproducible installs. |
| API | FastAPI | Team choice. Async, so streamed uploads keep memory flat. |
| Database access | psycopg 3 + plain SQL, no ORM | The pipeline uses window functions and bulk `COPY`. An ORM hides both. |
| Database migrations | Alembic (raw SQL with `op.execute`) | Standard. Handles table partitions. |
| CLI | Typer (`run-pipeline`, `import --now`) | Manual runs, demo, tests. |
| Dashboard | Next.js (`apps/dashboard`) | Already built. |
| Database | PostgreSQL 17 | Relational data, transactions across steps. One database: [mvp-flows.md](mvp-flows.md) section Store. |
| Database high availability | CloudNativePG (Kubernetes operator) | Primary + standby, automatic failover, backups, point-in-time restore. We do not write this. |
| File storage (inbox) | The customer's S3-compatible storage; SeaweedFS if they have none | One S3 API in the code. Banks often have storage already (e.g. NetApp StorageGRID, Dell ECS, Ceph). SeaweedFS = Apache-2.0. |
| Production runtime | Kubernetes + our Helm chart | Stays up when one machine fails. Rolling updates, no outage. Banks already run it (or OpenShift). |
| Dev and demo runtime | Docker Compose, one machine | Simple local development. Same images as production. |
| Work queue | `import_files` table in Postgres | Stores work safely, retries after a crash. No extra service. |
| Scheduler | Loop inside the worker container | No cron, no extra service. 1-min tick. |
| Locks | Postgres advisory lock for each site + lane | Sites run in parallel; one site never twice at once. |
| Log delivery (origin) | Vector agent, installed by the customer | Free (MPL-2.0), one binary, keeps data on disk while we are down. |
| Log delivery (CDN) | Vendor log push | Built into the CDN. Provider-neutral. |
| Upload | Streamed `POST /ingest` | The only method Vector and CDN push support. |
| Entry and TLS | The customer's ingress or Gateway API controller; Caddy in Compose | Banks use their own standard controller. Caddy is simple for dev. |
| Secrets | Kubernetes Secret, or the customer's Vault through External Secrets; `.env` in Compose | Fits what the customer already runs. |
| Monitoring | `/metrics` (Prometheus) + `/health` + JSON logs to stdout | The customer's own tools read them. |
| Backups | CloudNativePG to S3, point-in-time restore | Built into the operator. |
| LLM (recommendation text) | The customer's own key, or off (template text) | Banks may block outside calls. Template fallback exists (Flow 5). |
| Internet access | Offline mode: IP lists + bot registry bundled in each release | Banks often block outside calls. |

### Not used

| Not used | Why not |
|---|---|
| MinIO | Free community edition in maintenance mode (late 2025). License and support risk for banks. |
| Kafka, RabbitMQ, SQS | The Postgres table does the job ([mvp-flows.md](mvp-flows.md) 7.8). |
| Our own ingress controller | Banks have their own. ingress-nginx was retired in 2026. |
| ClickHouse | Only above ~1 B events/day ([mvp-flows.md](mvp-flows.md) S.5). |
| ORM | Hides the SQL the pipeline depends on. |

---

## Dev and demo: Docker Compose (one machine)

```
                        docker compose up
 ┌──────────────────────────────────────────────────────────────────────────┐
 │ Vector (test) ─┐                                                         │
 │ curl / CLI ────┼─► caddy :443 ──┬─ /ingest, /api/* ──► api (FastAPI)     │
 │ browser ───────┘   TLS, 50 MB   │                         │ stream files │
 │                    body limit   └─ /* ───────────► dashboard (Next.js)   │
 │                                                            ▼             │
 │                                                     seaweedfs (S3 API)   │
 │                                                            ▲ read files  │
 │ migrate (one-shot: alembic upgrade) ─► postgres 17 ◄── worker (loop)     │
 └──────────────────────────────────────────────────────────────────────────┘
```

- 6 services: `caddy`, `api`, `worker`, `dashboard`, `postgres`, `seaweedfs`, plus the one-shot `migrate`.
- `worker` = the `api` image with a different command.
- Workers: `replicas: N` by hand. No auto scaling.
- No backups and no failover. Demos and trials only, never production data. The README must say this.

## Production: Kubernetes + Helm

```
                    Customer Kubernetes cluster (3+ nodes)
 Vector / CDN ──► Ingress / Gateway (TLS) ──┬──► api ×2 ───────────────┐
 PM browser  ─────────────────────────────────► dashboard ×2          │ stream files
                                            │                          ▼
                                            │                S3-compatible storage
                                            │                          ▲
                                            └──► worker ×N ────────────┘ read files
                                                    │
                                                    ▼
                                Postgres (CloudNativePG: primary + standby, auto failover)
```

| Part | Kubernetes object |
|---|---|
| Entry and TLS | `Ingress` and `HTTPRoute` (both shipped); the customer's controller |
| api | Deployment ×2, rolling updates |
| worker | Deployment ×N |
| dashboard | Deployment ×2 |
| Postgres | CloudNativePG `Cluster` (primary + standby), backups to S3 |
| Migrations | Helm pre-upgrade Job (`alembic upgrade head`) |
| Secrets | Secret, or External Secrets from the customer's Vault |

### Compose vs Kubernetes (why both)

| | Docker Compose | Kubernetes |
|---|---|---|
| Machines | 1 | Many |
| A machine fails | Everything stops | Containers restart on another machine |
| Software update | Short outage | Rolling update, no outage |
| Postgres high availability | No | Yes (CloudNativePG) |
| Use | Dev, demo, trial | Customer production |

Ingest uptime is less critical than it looks: if we are down, Vector keeps the logs on its disk and sends them later. No data lost, only freshness. Uptime matters most for the dashboard and the database.

---

## Log senders (customer side)

The customer installs and runs the senders. We supply config files and a setup guide.

| Source | Sender | Who sets it up | We supply |
|---|---|---|---|
| CDN logs | The CDN's log push | Customer, in the CDN console | Endpoint URL, site token, field map |
| CDN that writes only to its own bucket | Our bucket reader (in the worker) | Customer gives read-only access to that bucket | Nothing extra |
| Origin logs | Vector on each origin server | Customer ops team | `vector.toml` + install guide |
| Old files, tests | Dashboard upload or CLI | Webzero PM | Nothing extra |

### Where Vector runs

It must run on the same machine as nginx: it reads the log file from the local disk.

| Customer setup | Vector runs as |
|---|---|
| VM or bare metal | systemd service |
| Docker | Sidecar container sharing the log volume |
| Kubernetes | DaemonSet (one pod on each node) |
| No agents allowed on origins | nginx `access_log syslog:server=…` (TCP) → one central Vector VM. UDP can lose lines. |

### `vector.toml` (draft)

```toml
[sources.nginx]
type    = "file"
include = ["/var/log/nginx/access.log"]

[sinks.webzero]
type     = "http"
inputs   = ["nginx"]
uri      = "https://<our-host>/ingest?site=<site_id>"
encoding.codec = "text"          # raw lines; our importer parses them
compression    = "gzip"
batch.timeout_secs = 30
batch.max_bytes    = 10_000_000
auth.strategy = "bearer"
auth.token    = "<site token>"
buffer.type     = "disk"
buffer.max_size = 1_073_741_824  # 1 GB on disk while our API is down
```

---

## Offline mode (PROPOSED)

Setting `OFFLINE=true`. Each outside call already has a fallback.

| Outside call | Used by | Offline behavior |
|---|---|---|
| Vendor IP lists (daily download) | Verify (Flow 2) | Bundled in each release; snapshot date in the evidence |
| Reverse DNS | Verify (Flow 2) | The customer's DNS server; if it cannot resolve public names → UNVERIFIED |
| LLM | Recommendations (Flow 5) | Off → template text |

## Open

- Offline mode: confirm.
- Helm chart: minimum Kubernetes version, and OpenShift support (security context rules).
