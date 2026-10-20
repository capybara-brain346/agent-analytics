# Deployment

This module covers how Agent Analytics runs inside one customer network: container images, Docker Compose (dev and demo), Kubernetes with Helm (production), and the log senders that the customer runs.
Input: the repo, the `api` and `dashboard` images, customer infrastructure. Output: a running stack that accepts logs on `POST /ingest` and serves the dashboard.
The managed (AWS) target uses the same images. Managed infrastructure is not written.

## Read this when

- You start or debug the stack with Docker Compose.
- You change `deploy/compose/docker-compose.yml`, `Caddyfile` or `seaweedfs-s3.json`.
- You change the Helm chart (`deploy/helm/agent-analytics/`) or its `values.yaml`.
- You change a Dockerfile (`apps/api/Dockerfile`, `deploy/dashboard/Dockerfile`).
- You add or change the origin log sender config (`deploy/vector/vector.toml`).
- You add a new environment variable that Compose or Helm must pass.
- You work on offline mode (no outside network).
- You write or change the setup guide `setup.md`.

For the list of technologies and the reason for each, see [architecture](../architecture/README.md).

## Code map

| Path | Purpose |
|---|---|
| `apps/api/Dockerfile` | One image for `api`, `worker` and `migrate`. |
| `deploy/dashboard/Dockerfile` | Dashboard image. Build context is `apps/dashboard`. |
| `deploy/dashboard/Dockerfile.dockerignore` | Excludes `node_modules`, `.next`, `tsconfig.tsbuildinfo` from the dashboard build. |
| `deploy/compose/docker-compose.yml` | Dev and demo stack. Has a default for every value. |
| `deploy/compose/Caddyfile` | TLS and routing for Compose. |
| `deploy/compose/seaweedfs-s3.json` | SeaweedFS S3 identity (access key `dev`, secret `dev-secret`). |
| `deploy/compose/.env.example` | Optional override values for Compose. |
| `deploy/helm/agent-analytics/Chart.yaml` | Chart metadata (`version` and `appVersion` `0.1.0`). |
| `deploy/helm/agent-analytics/values.yaml` | All chart settings. |
| `deploy/helm/agent-analytics/templates/api.yaml` | `api` Deployment and Service. |
| `deploy/helm/agent-analytics/templates/worker.yaml` | `worker` Deployment. |
| `deploy/helm/agent-analytics/templates/dashboard.yaml` | `dashboard` Deployment and Service. |
| `deploy/helm/agent-analytics/templates/migrate-job.yaml` | Migration Job (Helm hook). |
| `deploy/helm/agent-analytics/templates/postgres-cluster.yaml` | CloudNativePG `Cluster`. |
| `deploy/helm/agent-analytics/templates/ingress.yaml` | `Ingress` (enabled by default). |
| `deploy/helm/agent-analytics/templates/httproute.yaml` | Gateway API `HTTPRoute` (disabled by default). |
| `deploy/helm/agent-analytics/templates/_helpers.tpl` | Names, labels, shared `api` environment (`aa.apiEnv`). |
| `deploy/vector/vector.toml` | Origin log sender config for the customer. |
| `setup.md` | Step guide that tells an AI agent to start the Compose stack. Not a prompt. |
| `README.md` section "2. Run it" | Human run steps for Compose and local development. |
| `apps/api/src/config/settings.py` | Every environment variable and default (`Settings`). |
| `apps/api/src/routes/health.py` | `/livez` and `/health`. |
| `apps/api/src/routes/metrics.py` | `/metrics` (Prometheus). |
| `apps/api/src/services/pipeline/worker.py` | Worker loop. Gates the IP-list download on `offline`. |
| `apps/api/src/services/verify/ip_lists.py` | IP-list download. Uses bundled files when `offline`. |
| `apps/api/config/registry/ip-lists/` | Bundled vendor IP lists (`IP_LIST_DIR`). |

`deploy/cloudflare-pages/` is the live-site capture. It is not part of the runtime. See [testing](../testing/README.md).

## Data flow

### Compose (dev and demo, one machine)

```
                           docker compose up
 +--------------------------------------------------------------------------+
 | Vector (test) -+                                                         |
 | curl / CLI ----+--> caddy :443 --+-- /ingest /api/* /health /livez       |
 | browser -------+    TLS, 50 MB   |   /metrics --------> api (FastAPI)    |
 |                    body limit    |                        | stream files |
 |                                  +-- all other paths -> dashboard        |
 |                                                           v   (Next.js)   |
 |                                                    seaweedfs (S3 API)    |
 |                                                           ^ read files   |
 | migrate (one-shot: alembic upgrade head) --> postgres 17 <-- worker loop |
 +--------------------------------------------------------------------------+
```

### Kubernetes (production)

```
                    Customer Kubernetes cluster (3+ nodes)
 Vector / CDN --> Ingress or Gateway (TLS) --+--> api x2 ------------+
 PM browser  ---------------------------------+--> dashboard x2      | stream files
                                              |                      v
                                              |            S3-compatible storage
                                              |                      ^
                                              +--> worker xN --------+ read files
                                                        |
                                                        v
                           Postgres (CloudNativePG: primary + standby, auto failover)
```

### Log sender to inbox

```
 Sender (Vector or CDN push)        api                    Inbox (S3)       Postgres
        |                            |                        |                |
        |-- POST /ingest?site=ID --->|                        |                |
        |   Bearer site token, gzip  |-- stream, 64 KB parts->|                |
        |                            |-- insert import_files (status new) ---->|
        |<-------- 202 --------------|                        |                |
        |                            |                        |                |
        |  (api down: Vector keeps data in its disk buffer and sends later)    |
```

Worker steps after the insert: [ingestion](../ingestion/README.md) and [pipeline](../pipeline/README.md).

### Helm install and upgrade

```
 helm install/upgrade
        |
        +--> Cluster (CloudNativePG) --> Postgres + secret "<release>-pg-app" (key "uri")
        +--> Deployments: api, worker, dashboard (DATABASE_URL from "<release>-pg-app")
        +--> Ingress / HTTPRoute
        +--> Job "<release>-migrate": alembic upgrade head
             hook: post-install (first install), pre-upgrade (each upgrade)
```

## Rules and decisions

### Runtime

1. One set of images runs everywhere (Compose, Kubernetes, managed). Why: same code and same tests for all targets.
2. `worker` and `migrate` use the `api` image with another command. Why: one build, one lock file.
3. Dev and demo runtime is Docker Compose on one machine. Why: simple local development.
4. Production runtime is Kubernetes with the Helm chart in this repo. Why: it stays up when one machine fails and updates roll without an outage. Banks already run Kubernetes or OpenShift.
5. Compose has no backups and no failover. Use it for demos and trials only, never for production data. The README must say this. Why: one machine, no operator.
6. Workers scale by hand: `deploy.replicas` in Compose, `worker.replicas` in Helm. No auto scaling. Why: cap workers to fit the database connection limit [7.10].
7. No queue product and no scheduler service. The `import_files` table is the queue. A loop inside the worker is the scheduler. Why: see [pipeline](../pipeline/README.md) [7.8].
8. Ingest uptime is less critical than dashboard and database uptime. Why: when the API is down, Vector keeps logs on its disk and sends them later. Data is not lost. Only freshness drops.

### Compose

9. Compose needs no `.env` file. Every value has a `${VAR:-default}` in `docker-compose.yml`. The `env_file: .env` entry has `required: false`. Why: one command starts the stack. This needs Docker Compose v2.24 or later.
10. Copy `.env.example` to `.env` only to override a value. A `.env` value wins over a default.
11. `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` defaults (`dev`, `dev-secret`) must match `deploy/compose/seaweedfs-s3.json`. Why: SeaweedFS reads its keys from that file.
12. Caddy serves HTTPS on `localhost` with its own local CA certificate. The browser shows a "not secure" notice the first time. Why: dashboard browsers and some senders need HTTPS.
13. Caddy sends `/ingest`, `/api/*`, `/health`, `/livez`, `/metrics` to `api:8000` with a 50 MB request body limit. All other paths go to `dashboard:3000`.
14. `migrate` runs once (`restart: "no"`). `api` and `worker` start after it exits with code 0 (`service_completed_successfully`). `migrate` waits for the `postgres` health check.
15. The inbox store creates the bucket if it does not exist (`ensure_bucket` in `apps/api/src/store/inbox.py`, also called from `apps/api/src/services/importer/service.py`). Why: Compose needs no bucket setup step.

### Kubernetes and Helm

16. We ship the application charts only. We do not ship an ingress controller. `Ingress` and `HTTPRoute` are both in the chart. Why: banks use their own standard controller. ingress-nginx was retired in 2026.
17. Postgres runs as a CloudNativePG `Cluster` (PostgreSQL 17, primary + standby, automatic failover). The operator must be installed in the cluster. We do not write the failover code. Why: operator gives failover, backups and point-in-time restore.
18. `DATABASE_URL` comes from the operator secret `<release>-pg-app`, key `uri`.
19. Migrations run as a Helm hook Job (`helm.sh/hook: post-install,pre-upgrade`, delete policy `before-hook-creation,hook-succeeded`, `backoffLimit: 3`). Why: schema is ready before new pods serve traffic. `post-install` is used because the database does not exist before the first install.
20. The inbox is the customer's S3-compatible storage (for example NetApp StorageGRID, Dell ECS, Ceph). SeaweedFS is the fallback when the customer has none. Why: one S3 API in the code.
21. Secrets come from one Kubernetes Secret (`existingSecret`, default `agent-analytics`). The customer creates it by hand or with External Secrets from their Vault. Why: fits what the customer runs.
22. Monitoring is the customer's. The API gives `/metrics` (Prometheus), `/health` and JSON logs to stdout.
23. Backups use CloudNativePG `barmanObjectStore` to S3 (`postgres.backup.*`). Disabled by default.
24. The API probes use `/livez` (no database check). `/health` is for monitoring: it returns HTTP 503 with `"healthy":false` when the database fails or a lane is stale.

### Dockerfiles

25. `apps/api/Dockerfile`: base `python:3.14-slim`, `uv` copied from `ghcr.io/astral-sh/uv:0.12.19`, `uv sync --locked --no-install-project`, runs as non-root user `app` (uid `10001`), default command `uvicorn src.main:app --host 0.0.0.0 --port 8000 --no-access-log`. The image holds `alembic.ini`, `migrations/`, `config/` and `src/`.
26. Because `config/` (bot registry, IP lists, CDN field maps, site configs) is in the image, a change to these YAML files needs a new image.
27. `deploy/dashboard/Dockerfile`: two stages on `node:24-slim`. Stage 1 runs `npm ci` and `npm run build`. Stage 2 copies `/app`, runs as user `node`, command `npm start`, port `3000`.

### Log senders (customer side)

28. The customer sends. We never fetch from customer servers. We supply config files and a setup guide. Why: no SSH or credentials into customer hosts [1.14].
29. Origin logs: Vector on each origin server, run by the customer. Fluent Bit is also accepted. Vector sends raw lines. Our importer is the only parser [1.14].
30. The only upload method is the streamed `POST /ingest?site=<id>` with a bearer token for each site [1.15]. Why: it is the only method that Vector `http` and CDN HTTP push support.
31. Vector must run on the same machine as nginx. It reads the log file from local disk.

Sender matrix:

| Source | Sender | Who sets it up | We supply |
|---|---|---|---|
| CDN logs | The CDN's log push | Customer, in the CDN console | Endpoint URL, site token, field map |
| CDN that writes only to its own bucket | Our bucket reader (in the worker) | Customer gives read-only access to that bucket | Nothing extra |
| Origin logs | Vector on each origin server | Customer ops team | `vector.toml` and install guide |
| Old files, tests | Dashboard upload or CLI | Webzero PM | Nothing extra |

Where Vector runs:

| Customer setup | Vector runs as |
|---|---|
| VM or bare metal | systemd service |
| Docker | Sidecar container that shares the log volume |
| Kubernetes | DaemonSet (one pod on each node) |
| No agents allowed on origins | nginx `access_log syslog:server=...` (TCP) to one central Vector VM. UDP can lose lines. |

`deploy/vector/vector.toml` (placeholders `<our-host>`, `<site_id>`, `<site token>`):

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

`batch.max_bytes` (10 MB) stays below the `/ingest` limit (`INGEST_MAX_BYTES`, 50 MB, also the Caddy limit).

### Compose and Kubernetes compared

| | Docker Compose | Kubernetes |
|---|---|---|
| Machines | 1 | Many |
| A machine fails | Everything stops | Containers restart on another machine |
| Software update | Short outage | Rolling update, no outage |
| Postgres high availability | No | Yes (CloudNativePG) |
| Use | Dev, demo, trial | Customer production |

### Compose services

| Service | Image | Port on host | Notes |
|---|---|---|---|
| `caddy` | `caddy:2` | 80, 443 | Volume `caddy-data`. Starts after `api` and `dashboard`. |
| `api` | `agent-analytics-api:dev` (built from `apps/api`) | none | Starts after `migrate` and `seaweedfs`. |
| `worker` | same image | none | Command `python -m src.cli worker`. `deploy.replicas: 1`. |
| `migrate` | same image | none | Command `alembic upgrade head`. One-shot. |
| `dashboard` | `agent-analytics-dashboard:dev` | none | `API_URL=http://api:8000`, `API_TOKEN` from `${API_TOKEN:-}`. |
| `postgres` | `postgres:17` | 5432 | Volume `postgres-data`. Health check `pg_isready`. |
| `seaweedfs` | `chrislusf/seaweedfs:latest` | 8333 | Command `server -s3 -s3.config=... -dir=/data`. Volume `seaweedfs-data`. |

### Helm objects

| Part | Kubernetes object | Default |
|---|---|---|
| Entry and TLS | `Ingress` and `HTTPRoute` (customer's controller) | `Ingress` on, `HTTPRoute` off |
| api | Deployment, `RollingUpdate`, Service `<release>-api:8000` | 2 replicas |
| worker | Deployment | 2 replicas |
| dashboard | Deployment, `RollingUpdate`, Service `<release>-dashboard:3000` | 2 replicas |
| Postgres | CloudNativePG `Cluster` `<release>-pg`, image `ghcr.io/cloudnative-pg/postgresql:17`, database and owner `agent_analytics` | 2 instances, 100Gi |
| Migrations | Hook Job `<release>-migrate` | always on |
| Secrets | Secret `existingSecret` | `agent-analytics` |

Routing in `Ingress` and `HTTPRoute`: paths `/ingest`, `/api`, `/health`, `/metrics` (prefix) go to the api Service. Path `/` goes to the dashboard Service. All pods set `runAsNonRoot: true`.

## Configuration

### Compose variables (`docker-compose.yml`, override in `deploy/compose/.env`)

| Variable | Default | Effect |
|---|---|---|
| `POSTGRES_USER` | `agent_analytics` | Postgres user. Also in `DATABASE_URL`. |
| `POSTGRES_PASSWORD` | `agent_analytics` | Postgres password. Also in `DATABASE_URL`. |
| `POSTGRES_DB` | `agent_analytics` | Database name. |
| `S3_BUCKET` | `agent-analytics-inbox` | Inbox bucket. |
| `S3_ACCESS_KEY_ID` | `dev` | Must match `seaweedfs-s3.json`. |
| `S3_SECRET_ACCESS_KEY` | `dev-secret` | Must match `seaweedfs-s3.json`. |
| `LOG_LEVEL` | `INFO` | Log level of `api`, `worker`, `migrate`. |
| `OFFLINE` | `false` | Offline mode flag. See "Offline mode". |
| `API_TOKEN` | empty (unset) | Bearer token for `/api/*`. The dashboard server adds it to its calls. Unset = open (dev only). |
| `OPENROUTER_API_KEY`, `LLM_MODEL` | unset | Set both for LLM text. Else template text. Both come from `.env` through `env_file`. |

Fixed in Compose (no variable): `S3_ENDPOINT_URL=http://seaweedfs:8333`, `API_URL=http://api:8000` (dashboard).

### Helm values (`values.yaml`)

| Key | Default | Effect |
|---|---|---|
| `image.api` | `agent-analytics-api:0.1.0` | Image for `api`, `worker`, `migrate`. |
| `image.dashboard` | `agent-analytics-dashboard:0.1.0` | Dashboard image. |
| `image.pullPolicy` | `IfNotPresent` | Pull policy. |
| `api.replicas` | `2` | api pods. |
| `worker.replicas` | `2` | worker pods. Cap to fit the database connection limit [7.10]. |
| `dashboard.replicas` | `2` | dashboard pods. |
| `api.resources`, `worker.resources`, `dashboard.resources` | `{}` | Container resources. |
| `host` | `agent-analytics.example.internal` | Host name for `Ingress` and `HTTPRoute`. |
| `ingress.enabled` | `true` | Make the `Ingress`. |
| `ingress.className` | `""` | Ingress class of the customer's controller. |
| `ingress.tlsSecretName` | `""` | TLS secret. Empty = no `tls` block. |
| `httpRoute.enabled` | `false` | Make the `HTTPRoute`. |
| `httpRoute.parentRefs` | `[]` | The customer's Gateway. |
| `postgres.instances` | `2` | CloudNativePG instances. |
| `postgres.storageSize` | `100Gi` | Volume size for each instance. |
| `postgres.backup.enabled` | `false` | Add `barmanObjectStore` backup. |
| `postgres.backup.destinationPath` | `""` | `s3://bucket/path`. |
| `postgres.backup.endpointURL` | `""` | S3 endpoint for backups. |
| `postgres.backup.credentialsSecret` | `""` | Secret with keys `ACCESS_KEY_ID` and `ACCESS_SECRET_KEY`. |
| `inbox.endpointURL` | `""` | S3 endpoint (`S3_ENDPOINT_URL`). |
| `inbox.bucket` | `agent-analytics-inbox` | `S3_BUCKET`. |
| `inbox.region` | `us-east-1` | `S3_REGION`. |
| `existingSecret` | `agent-analytics` | Secret name. Keys: `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `API_TOKEN`, optional `OPENROUTER_API_KEY`. `api` and `worker` load all keys with `envFrom`. The dashboard reads `API_TOKEN` (optional key). |
| `offline` | `false` | `OFFLINE`. |
| `logLevel` | `INFO` | `LOG_LEVEL`. |
| `llm.model` | `""` | `LLM_MODEL`. Empty = the variable is not set = template text. |
| `llm.baseURL` | `https://openrouter.ai/api/v1` | `LLM_BASE_URL`. |

### API settings that matter for deployment (`apps/api/src/config/settings.py`)

| Setting (env var) | Default | Effect |
|---|---|---|
| `DATABASE_URL` | `postgresql://agent_analytics:agent_analytics@localhost:5432/agent_analytics` | Postgres connection. Compose and Helm set it. |
| `DB_POOL_MAX_SIZE` | `10` | Connections for each process. Multiply by pod count to stay under the Postgres limit [7.10]. |
| `S3_ENDPOINT_URL` | `None` (AWS S3) | S3 endpoint. |
| `S3_REGION` | `us-east-1` | S3 region. |
| `S3_BUCKET` | `agent-analytics-inbox` | Inbox bucket. |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | `None` | S3 keys. |
| `INGEST_MAX_BYTES` | `52428800` (50 MB) | `/ingest` body limit. Keep the proxy limit equal. |
| `TICK_SECONDS` | `60` | Worker tick. |
| `BUCKET_READER_ENABLED` | `false` | Turn on the bucket reader. Not set by Compose or Helm. |
| `BUCKET_READER_INTERVAL_SECONDS` | `60` | Bucket reader period. |
| `BUCKET_READER_PREFIX` | `""` | Key prefix to read. |
| `API_TOKEN` | `None` | Bearer token for `/api/*`. Unset = open and a warning is logged at start. |
| `OPENROUTER_API_KEY` | `None` | LLM key. |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter or a compatible gateway. |
| `LLM_MODEL` | `None` | Model ID. `None` = template text. |
| `LOG_LEVEL` | `INFO` | Log level. |
| `OFFLINE` | `false` | See "Offline mode". |
| `IP_LIST_DIR` | `apps/api/config/registry/ip-lists` | Folder of bundled IP lists. |

### Dashboard container

| Variable | Default | Effect |
|---|---|---|
| `API_URL` | `http://localhost:8000` (code default) | Base URL the proxy `/dashboard-api` forwards to. Compose: `http://api:8000`. Helm: `http://<release>-api:8000`. |
| `API_TOKEN` | unset | Bearer token added to forwarded calls. Must equal the API's `API_TOKEN`. |

## Interfaces

Endpoints that deployment must route or probe:

| Endpoint | Auth | Use |
|---|---|---|
| `POST /ingest?site=<id>` | site bearer token | Senders. Reply `202`. |
| `GET /livez` | none | Liveness and readiness (Helm). Returns `{"status":"ok"}`. |
| `GET /health` | none | Monitoring. `503` and `"healthy":false` when the database fails or a lane is stale. After a fresh start it can be `503` until the worker finishes its first run. |
| `GET /metrics` | none | Prometheus. |
| `/api/*` | `API_TOKEN` bearer (open if unset) | Dashboard. |

Commands:

| Command | Where | Effect |
|---|---|---|
| `docker compose up --build` | `deploy/compose` | Start the full stack on https://localhost. |
| `docker compose down` / `down -v` | `deploy/compose` | Stop, keep data / stop and delete data. |
| `docker compose up -d postgres seaweedfs` | `deploy/compose` | Start only the back-end dependencies for local development. |
| `python -m src.cli worker [--lanes fast\|slow\|all]` | `api` image | Worker. Default `all`. `--lanes fast` or `--lanes slow` runs one loop: use two Deployments to scale lanes apart. |
| `alembic upgrade head` | `api` image | Migrations. |
| `python -m src.cli download-ip-lists` | `api` image | Download (or, when `OFFLINE=true`, load bundled) IP-list snapshots once. |
| `docker compose exec worker python -m src.cli run-recommendations --site example --window 14d` | `deploy/compose` | Make recommendations from sample data. "Generate now" looks only at the last 6 hours. |

### `setup.md`

`setup.md` (repo root) is a guide for an AI agent. The agent must:

1. Check `docker`, `docker compose version` (v2.24 or later), the daemon, and free host ports 80, 443, 5432, 8333.
2. Not create a `.env`. Create `deploy/compose/.env` only when the user gives an LLM key (`OPENROUTER_API_KEY` and `LLM_MODEL`, default `anthropic/claude-sonnet-5.5`). The key is optional.
3. Run `docker compose up --build -d` in `deploy/compose`.
4. Check `docker compose ps -a`: `caddy`, `api`, `worker`, `dashboard`, `seaweedfs` are `Up`, `postgres` is `Up (healthy)`, `migrate` is `Exited (0)`. Then `curl -sk https://localhost/health` (retry up to 2 minutes) and `https://localhost/` (200).
5. Tell the user to open https://localhost and to continue past the certificate warning.

Rules in `setup.md`: Docker Compose only (no Kubernetes, Helm, Vector); no repo file changes; no commit, branch or push. Sample data: logs in `samples/logs/` are synthetic and cover 2026-10-12 to 2026-10-18. Dashboard time ranges count back from now, so old sample data falls outside `7d` later. If you change Compose services, ports or the health check, update `setup.md` Step 1 and Step 4.

## Offline mode

Offline mode is a single setting `OFFLINE=true` for customers who block outside calls. Each outside call needs a fallback.

| Outside call | Used by | Offline behavior | State in code |
|---|---|---|---|
| Vendor IP lists (daily download) | verification | Bundled in each release. Snapshot date goes in the evidence. | `download_snapshots` loads the bundled files from `IP_LIST_DIR` and makes no network call when `OFFLINE=true`. The worker does not run this job when `OFFLINE=true` (see below). |
| Reverse DNS | verification | The customer's DNS server. If it cannot resolve public names: `UNVERIFIED`. | Not gated by `OFFLINE`. A DNS error gives `UNVERIFIED` and is retried after `UNVERIFIED_RETRY_MINUTES` (60). |
| LLM | recommendations | Off: template text. | Not gated by `OFFLINE`. Template text is used when `LLM_MODEL` or `OPENROUTER_API_KEY` is unset. |

What exists in the code:

- Setting `offline: bool = False` in `apps/api/src/config/settings.py`. Compose passes `OFFLINE`. Helm passes `offline`.
- `apps/api/src/services/verify/ip_lists.py`: with `offline` no HTTP client is made and each IP-list source is read from `IP_LIST_DIR`. Without `offline`, a failed download falls back to the bundled file only when no snapshot exists yet.
- `apps/api/src/services/pipeline/worker.py` `_maintenance`: with `offline` the job `download_ip_lists` is removed from the daily jobs. To load the bundled snapshots, run `python -m src.cli download-ip-lists` once after install and after each release.
- Tests: `tests/verify/test_ip_lists.py` (`test_offline_loads_bundled_without_network`, `test_offline_custom_dir`). `tests/e2e/conftest.py` sets `OFFLINE=true`.

## Known limits

- Compose: no backups, no failover, no auto scaling. Postgres (5432) and SeaweedFS (8333) are published on the host. Default passwords and S3 keys are for dev only.
- `setup.md` needs Docker Compose v2.24 or later (optional `env_file`). Rootless Docker cannot bind ports 80 and 443 by default.
- Helm: `resources` are empty by default. No `PodDisruptionBudget`, affinity or `NetworkPolicy` in the chart. The worker and dashboard Deployments have no probes. The migrate Job does not load `existingSecret`.
- Helm: the chart has no value for the bucket reader settings, site config files or other `Settings` fields. Site configs are in the image (`apps/api/config/`).
- Helm: routing does not include `/livez`. The Kubernetes probes call the pod directly, so this does not affect them.
- `/metrics`, `/health` and `/livez` have no auth. Restrict them at the ingress when needed.
- Rate limits and byte quotas for `/ingest` are in `Settings` (`INGEST_RATE_PER_MINUTE`, `INGEST_BYTES_PER_DAY`). See [ingestion](../ingestion/README.md).

## Open questions

- Offline mode: confirm the design with the customer (bundled IP lists with snapshot date in evidence, customer DNS, LLM off).
- Helm chart: minimum Kubernetes version.
- Helm chart: OpenShift support (security context rules).

## How to change

| Task | Steps |
|---|---|
| Add an environment variable to the API | Add the field in `apps/api/src/config/settings.py`. Add it to `aa.apiEnv` in `_helpers.tpl` and a key in `values.yaml` (or to `existingSecret` for secrets). Add `${VAR:-default}` to `x-api-image` in `docker-compose.yml` and a line in `.env.example`. Update the tables in this file. |
| Add an API secret | Add the key to `existingSecret` (Helm reads it with `envFrom`). In Compose it comes from `.env` through `env_file`. |
| Change the upload body limit | Change `INGEST_MAX_BYTES`, `max_size` in `Caddyfile`, and the controller limit in the customer's ingress. Keep Vector `batch.max_bytes` below it. |
| Add a route to the api | Add the path to the `@backend` matcher in `Caddyfile`, and to the path lists in `ingress.yaml` and `httproute.yaml`. |
| Scale workers | Compose: `deploy.replicas` of `worker`. Helm: `worker.replicas`. Check `DB_POOL_MAX_SIZE` times pod count against the Postgres limit. |
| Scale one lane apart | Run two worker Deployments with `--lanes fast` and `--lanes slow`. |
| Change the inbox storage | Set `inbox.endpointURL`, `inbox.bucket`, `inbox.region` in Helm and the keys in `existingSecret`. |
| Turn on backups | Set `postgres.backup.*` in Helm. Create the credentials Secret with keys `ACCESS_KEY_ID` and `ACCESS_SECRET_KEY`. |
| Change a base image or `uv` version | Edit the Dockerfile. Rebuild with `docker compose build`. |
| Change the sender config | Edit `deploy/vector/vector.toml`. Keep `encoding.codec = "text"` (raw lines) and the bearer auth. |
| Change a bot, IP list or site config | Edit YAML in `apps/api/config/`. Rebuild the api image. See [verification](../verification/README.md). |

## Tests

There are no automated tests for Compose, Helm or Vector files. Check by hand:

```sh
cd deploy/compose && docker compose config          # Compose resolves with no .env
cd deploy/compose && docker compose up --build -d   # then follow setup.md Step 4
helm template deploy/helm/agent-analytics           # needs helm; render the chart
```

Offline mode tests (from `apps/api`, need Postgres on port 55432):

```sh
uv run pytest tests/verify/test_ip_lists.py
```

See [testing](../testing/README.md).

## Related modules

- [architecture](../architecture/README.md): technologies and why, "not used" list.
- [ingestion](../ingestion/README.md): `POST /ingest`, inbox, bucket reader, importer.
- [pipeline](../pipeline/README.md): worker loop, locks, scheduler.
- [store](../store/README.md): Postgres, inbox access, migrations.
- [verification](../verification/README.md): IP lists and reverse DNS.
- [recommendations](../recommendations/README.md): LLM text and template fallback.
- [api](../api/README.md): routes, auth, health.
- [dashboard](../dashboard/README.md): `/dashboard-api` proxy, `API_URL`, `API_TOKEN`.
- [testing](../testing/README.md): test setup, live-site capture.
