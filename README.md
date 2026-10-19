# Agent Analytics

> Can we turn observable AI-agent traffic into trustworthy evidence, and use that evidence to decide which journeys Webzero should test next?

Agent Analytics reads CDN and origin access logs. It finds AI agents and bots, verifies who they are, rebuilds what they did, and ranks the journeys to test next. Every claim has a label: **Observed**, **Inferred** or **Unknown**.

Built in a 5-day sprint for the Webzero engineering assignment ([docs/task.pdf](docs/task.pdf)).

```
 access logs ──► verified identity ──► sessions & journeys ──► ranked test recommendations
 (CDN + origin)   (IP list / rDNS)      (only where evidence     (each one links to the
                                         permits)                 exact log lines)
```

---

## Contents

1. [Result against the brief](#1-result-against-the-brief)
2. [Run it](#2-run-it)
3. [Architecture](#3-architecture)
4. [How one request becomes evidence](#4-how-one-request-becomes-evidence)
5. [Architecture decisions](#5-architecture-decisions)
6. [Test data and tests](#6-test-data-and-tests)
7. [Limits and path to production](#7-limits-and-path-to-production)
8. [Repository map and docs](#8-repository-map-and-docs)

---

## 1. Result against the brief

| Definition of done (PDF §09) | Where it is |
|---|---|
| Ingests real HTTP access logs through a documented, reproducible path | `POST /ingest` (Vector, CDN push), dashboard upload, CLI. All three use one inbox and one parser. |
| Normalises every event into one internal schema | One provider-neutral `events` table. CDN vendor differences live in YAML field maps only. |
| Classifies traffic, with evidence and confidence | 6 classes. Rule ID, rule version, verdict method and evidence text are stored on each verdict row. |
| Meaningful analytics in a working interface | Next.js dashboard, 6 sections, reads the live API. |
| Inspect any event and its related activity | Every number links to Activity explorer → Session detail → Event detail. |
| At least three evidence-linked recommendations | 5 patterns (P1–P5). Sample data triggers all of them. |
| Separates observed facts, hypotheses and unknowns | Labels in the API and the UI. "Claims to be X, unverified" until verified. |
| Automated tests for pipeline and classification | 492 pytest tests, including a full end-to-end pipeline test. |
| Handles sensitive fields; documents security gaps | Token auth, input limits, rejects without line text. Gaps listed in [§7](#7-limits-and-path-to-production). |
| Another engineer can run it from the handover | [§2](#2-run-it): one Compose command, committed sample logs. |

---

## 2. Run it

### Full stack (Docker Compose)

```sh
cd deploy/compose
cp .env.example .env
docker compose up --build
```

Open https://localhost (Caddy local CA). Then:

1. **Data & pipeline → Sources.** Drag files from [`samples/logs/`](samples/logs) onto the page.
2. Wait 1 min. The worker imports, pairs, verifies, classifies and builds the views.
3. **Recommendations → Generate now.**

The sample logs cover 2026-10-12 to 2026-10-18. Dashboard ranges count back from now, so select a range that includes these dates.

> Compose has no backups and no failover. Use it for dev, demo and trials only.

### Local development

```sh
# Back end (needs Postgres + S3 from Compose)
cd apps/api
uv sync && cp .env.example .env
docker compose -f ../../deploy/compose/docker-compose.yml up -d postgres seaweedfs
uv run alembic upgrade head
uv run uvicorn src.main:app --reload

# Load all sample logs and run the pipeline now (no wait for the scheduler)
uv run python -m src.cli import ../../samples/logs --now
uv run python -m src.cli run-pipeline fast --site example
uv run python -m src.cli run-recommendations --site example

# Dashboard
cd ../dashboard
npm install && npm run dev          # http://localhost:3000/overview
```

Optional: set `OPENROUTER_API_KEY` and `LLM_MODEL` for LLM-written recommendation text. Without them, the system uses template text.

---

## 3. Architecture

### System

```
  CUSTOMER SIDE                         AGENT ANALYTICS
 ┌──────────────────────┐   gzip chunks   ┌──────────────────────────────────────────────────────┐
 │ CDN log push ────────┼──────┐          │                                                      │
 │ nginx ─► Vector ─────┼──────┼─────────►│ api  POST /ingest ──stream──► Inbox (S3 API)         │
 │ CDN bucket ◄─ read ──┼──┐   │  token,  │      (202, no parsing)            │                  │
 └──────────────────────┘  │   │  quota   │                                   │ import_files     │
   PM: upload · CLI ───────┼───┘          │                                   ▼ (= the queue)    │
                           └─────────────►│ worker ─ FAST LANE (1 min) ───────────────────────┐  │
                                          │          import → pair → verify → classify → views│  │
                                          │        ─ SLOW LANE (6 h / on demand) ──────────┐  │  │
                                          │          recommendations ── LLM text (optional)│  │  │
                                          │                                                ▼  ▼  │
                                          │                                   PostgreSQL 17      │
                                          │                                                │     │
                                          │ api  GET /api/* (read only) ◄──────────────────┘     │
                                          └────────────────┬─────────────────────────────────────┘
                                                           ▼
                                   dashboard (Next.js) ── same-origin proxy ── PM / engineer / agent
```

Three processes, one image: `api`, `worker`, `migrate`. Plus `dashboard`, `postgres` and S3-compatible storage. No queue product, no cron.

### Pipeline stages (PDF §07 reference → this build)

```
 1 Collect ─► 2 Ingest ─► 3 Normalise ─► 4 Classify ─► 5 Sessionise ─► 6 Analyse ─► 7 Recommend ─► 8 Dashboard
 Vector,     /ingest,     adapters +     verify +      activity        hourly        5 patterns,   every number
 CDN push,   inbox,       field map,     classify      reconstruction  page/agent/   score, LLM    links to its
 upload,     sha256       dedupe,        (Flows 2–3)   (Flow 4)        journey       text          evidence
 CLI         (Flow 1)     pair (1b)                                    views         (Flow 5)      (Flow 6)
```

### Scheduling (Flow 7)

```
 worker loop (every TICK_SECONDS)
   │
   ├─ SELECT site FROM site_work … FOR UPDATE SKIP LOCKED   ◄─ waited longest = first
   ├─ advisory lock (site + lane) ── taken? ──► skip this tick
   ├─ step 1 … step N   each step = 1 transaction, "not done yet" work only
   │     └─ step fails ──► run = failed, later steps skip; next tick = retry
   └─ release lock

 3 failed runs in a row ──► alert      no data for 1 h from a source ──► alert
 /health: last success per site + lane; > 15 min = unhealthy
```

---

## 4. How one request becomes evidence

### Ingest (sequence)

```
 Sender (Vector/CDN)     api /ingest             Inbox (S3)       Postgres          worker
       │ POST chunk + token  │                       │                │                 │
       │────────────────────►│ check token, rate     │                │                 │
       │                     │ stream 64 KB parts ──►│                │                 │
       │                     │ sha256 while streaming│                │                 │
       │                     │ INSERT import_files (sha256 UNIQUE) ──►│                 │
       │◄──── 202 ───────────│   duplicate → 200 "already have it"    │                 │
       │                     │                       │                │◄── tick: status │
       │                     │                       │◄── read file ──┼──── = new ──────│
       │                     │                       │                │◄── parse, dedupe│
       │                     │                       │                │    COPY events  │
```

### Per line

```
 raw line ─► adapter (origin · CDN field map) ─► validate ─► dedupe ─► event
                 │ wrong shape                     │ bad value   │ same line key
                 ▼                                 ▼             ▼
            reject: line no. + reason (no line text)        counted, skipped
```

### CDN + origin pairing (Flow 1b)

```
 CDN line ──── edge_request_id + method + path, ±5 s ──── origin line
                               │
             ┌─────────────────┼──────────────────┬──────────────────────┐
             ▼                 ▼                  ▼                      ▼
        PAIRED event      CDN only           CDN only              ORIGIN only
        edge + origin     (blocked at edge)  (cache hit)           (flag: cdn_bypass)
        status
```

### Identity: verify, then classify (Flows 2–3)

```
 client_key = (User-Agent, IP)          ◄─ one check per client, not per line
      │
      ▼
 UA matches registry? ── no ──────────────────────────────────────► UNKNOWN
      │ yes: "claims GPTBot"
      ▼
 vendor publishes ─┬─ IP list ─► IP in snapshot?  yes ► VERIFIED   no ► SPOOFED
                   ├─ rDNS ────► PTR + forward match ► VERIFIED    no ► SPOOFED
                   │             DNS error / timeout ─────────────────► UNVERIFIED
                   └─ nothing ────────────────────────────────────────► CLAIMED
      │
      ▼  (first match wins, rule_version stored)
 SPOOFED ──────────────────────────────────────► 6 Unknown (flag: spoofed)
 search crawler + VERIFIED ────────────────────► 1 Verified search crawler
 search crawler, not verified ─────────────────► 3 Other identifiable bot
 AI crawler / agent client ────────────────────► 2 Known AI crawler   (confidence = verdict)
 other bot / library UA ───────────────────────► 3 Other identifiable bot
 headless UA, or edge says bot + browser UA ───► 4 Browser automation / agent-like
 browser UA + edge says human ─────────────────► 5 Ordinary browser
 anything else ────────────────────────────────► 6 Unknown ("browser UA, not confirmed human")
```

Verdicts are **append-only**. A new IP-list snapshot adds a new row. Old events keep the verdict that was true at their time.

### Activity reconstruction (Flow 4)

```
 events + verdicts
   ▼
 same client?  client_key (IPv6 → /64)          no UA or IP ──► not grouped
   ▼
 same visit?   gap > 30 min (agent clients: 2 min) = new session
   ▼
 session facts: pages in order · retries · loops · key pages · conversion reached · gaps
   ▼
 open_sessions (upsert while active) ──closed──► sessions (append once)
 page_stats · agents · journey_steps: hourly rows, only the current hour changes
```

Shared IPs (CGN, cloud egress) lower session confidence. Each session lists its gaps, for example "outcome unknown".

### Recommendations (Flow 5)

```
 ~1 M log lines ─► events ─► sessions ─► views ─► 5 pattern queries ─► ~20 candidates
                                                                         │
     ┌───────────────────────────────────────────────────────────────────┘
     ▼
 SCORE = Impact × Frequency × Severity × Confidence          (code, each factor shown)
     ▼
 FACT BUNDLE (exact SQL facts + sample event IDs)            (code)
     ▼
 LLM writes 4 text fields ─► VALIDATOR: every number, path, agent name in the bundle?
                                 ├─ yes ─► LLM text
                                 └─ no / LLM off ─► template text
     ▼
 ranked run, stored append-only (new / still open / gone vs previous run)
```

| Pattern | Trigger | Hypothesis |
|---|---|---|
| P1 Product discovery | AI sessions read ≥ 3 key pages, never reach conversion | Pages lack usable next steps |
| P2 Blocked access | Verified/AI clients get ≥ 5 × 403/429 on an allowed key page | Restrictions block legitimate discovery |
| P3 Broken navigation | ≥ 3 sessions retry or loop on a journey step | A route is broken |
| P4 Content discoverability | Key sitemap pages never fetched, or thin responses | Content is not reachable |
| P5 Full-journey simulation | Critical journey started, end not visible in logs | Only simulation can measure it |

Code fills facts (test, evidence, priority, confidence). The LLM writes only reason, potential issue, suggested validation and next action. The win condition never depends on the LLM.

---

## 5. Architecture decisions

Full record with reasons: [docs/mvp-flows.md](docs/mvp-flows.md) (decision IDs in brackets).

| Decision | Rejected alternative | Why |
|---|---|---|
| **Access logs (CDN + origin) as the collection path** [1.1, 1b.1] | JS snippet, middleware | Logs see crawlers that do not run JavaScript. Pairing shows edge blocks and origin failures for the same request. |
| **Customer pushes; we never fetch** [1.14] | SSH / pull from customer hosts | No credentials into customer hosts. Vector buffers on disk while we are down. |
| **Micro-batches every 30 s** [1.13] | Per-line stream (Kafka) | CDN push sets a 30 s – 5 min floor anyway. A stream needs a broker and exactly-once logic. |
| **One PostgreSQL** [S.1] | Separate log database (ClickHouse) | Steps need transactions across events, verdicts and files. Postgres handles ~10 M lines/day with daily partitions. ClickHouse is the measured scale path [S.5]. |
| **`import_files` table is the queue** [7.8] | SQS, RabbitMQ | `FOR UPDATE SKIP LOCKED` gives safe parallel work and crash retry. No second list to keep in sync. |
| **Worker loop as scheduler** [7.1] | cron, Airflow | No extra service. Advisory lock per site + lane: sites run in parallel, one site never twice. |
| **Provider-neutral schema; vendors in YAML** [1b.4] | Cloudflare-shaped model | PDF §03.A. A new CDN = a new field map, no code change. |
| **Bot registry as data** [2.10, 3.3] | Bot names in code | PDF §03.B. New bot = YAML edit. Rule order stays code, with `rule_version`. |
| **Verify by IP list first, then rDNS** [2.4, 2.6] | Trust the User-Agent | A UA is a claim. DNS failure = UNVERIFIED, not SPOOFED. |
| **Append-only verdicts and recommendation runs** [2.8, 5.4] | Upsert latest | Auditability: Monday's verdict stays true for Monday's events. |
| **Browser UA without edge signal = Unknown** [3.6] | Assume human | Honest. A UA is a claim. |
| **Incremental views: open/closed sessions, hourly rows** [4.1] | Full rebuild each run | Cost grows with active visits, not with history. |
| **Rules find; LLM only writes text; validator checks it** [5.7, 5.8] | LLM ranks or finds patterns | Facts can never be invented. Template fallback for offline banks. |
| **Plain SQL (psycopg 3), no ORM** | SQLAlchemy ORM | Pipeline needs window functions and bulk `COPY`. |
| **Compose for demo, Helm + CloudNativePG for production** | Managed cloud only | Target buyers (banks) run on-prem Kubernetes. Same images for both. |

---

## 6. Test data and tests

### Sample logs ([samples/logs/README.md](samples/logs/README.md))

One week, site `example`, 85 files, ~1 M lines, all fictional. Each scenario proves one behaviour.

| Scenario | Proves |
|---|---|
| `humans` | Browser sessions, journeys, conversions |
| `crawlers` | OpenAI/Perplexity bots VERIFIED by IP list; Anthropic bots CLAIMED; Googlebot needs rDNS |
| `spoof` | Fake Googlebot/GPTBot → SPOOFED or UNVERIFIED; 35 % blocked at the CDN |
| `failures` | 403 on key pages, 404 retries, 500 on `/signup`, redirect loops → all 5 patterns |
| `coverage` | Shared NAT IPs, CDN bypass, origin log gap, resent file (dedupe) |
| `edge` | Parser edge cases: bad JSON, bad timestamps, > 64 KB line, IPv6, unicode |

### Commands

```sh
# Back end: needs Postgres on :55432 (see apps/api/README.md)
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run pytest

# Dashboard
cd apps/dashboard && npm run lint && npm test && npm run build
```

| Suite | Covers |
|---|---|
| `tests/e2e/test_pipeline_e2e.py` | ingest → import → pair → verify → classify → views → recommendations → API |
| `tests/classify`, `tests/verify` | Rule order, spoofed UAs, IP lists, rDNS |
| `tests/importer`, `tests/ingest` | Adapters, dedupe, rejects, quota, rate limit, delete |
| `tests/reconstruction`, `tests/recommendations` | Sessions, retries, loops, the 5 patterns, scoring, LLM validator |
| `tests/pipeline` | Locks, stale runs, alerts, retention, health |

Each test session creates its own database and removes it at the end.

---

## 7. Limits and path to production

### What the data cannot prove

| Unknown | Why |
|---|---|
| Task completion | A 200 is not success. Logs show "reached step N", never "done". |
| Undeclared bots with a browser UA | No UA claim and no edge signal → class 6 Unknown. |
| Bots with no published IP list or rDNS | Stay CLAIMED (e.g. Anthropic in the sample data). |
| Same IP ≠ same agent | Sessions are inferred; shared IPs lower confidence. |
| Old events vs new IP lists | Verify uses the latest snapshot; its date is in the evidence. |

### Security gaps (known, documented)

| Gap | Required before customer data |
|---|---|
| Raw IPs and full URLs with query strings are stored [1.12] | IP hashing or masking, query-string stripping |
| `/api/*` is open when `API_TOKEN` is unset (logs a warning) | Always set it; add SSO and roles |
| Ingest rate limit is per API process | Shared limiter (Postgres or Redis) with many replicas |
| No HTTP message signature check (RFC 9421) | Add when agents send signature headers |

### Path to production (priority order)

1. Redaction at import: hash IPs, strip query strings.
2. SSO and role-based access on the dashboard and API.
3. Tune thresholds and the pairing window on real customer traffic.
4. Match each event to the IP-list snapshot of its own date.
5. Managed (multi-tenant) deployment. Every table already has `site_id`.
6. Scale path on measured need only: bigger Postgres → TimescaleDB compression → ClickHouse for events.

---

## 8. Repository map and docs

```
apps/
  api/                 Python 3.14 · FastAPI · psycopg 3 · Alembic · Typer
    src/routes/        /ingest, /api/*, /health, /metrics
    src/services/      one folder per pipeline step (importer, pairing, verify, classify,
                       reconstruction, recommendations, pipeline, alerts, cleanup)
    src/store/         all SQL and S3 access (one module = one place to change the store)
    config/            YAML: bot registry, IP lists, CDN field maps, site configs
    migrations/        Alembic, raw SQL, daily-partitioned events
    tests/             pytest: unit, API, e2e
  dashboard/           Next.js 16 · React 19 · TypeScript · shadcn/ui
deploy/
  compose/             dev and demo stack (Caddy, SeaweedFS, Postgres)
  helm/                production chart (CloudNativePG, Ingress, HTTPRoute)
  vector/              origin log sender config for the customer
samples/logs/          one week of fictional CDN + origin logs
docs/                  brief, flows, dashboard spec, on-prem, design
```

| Document | Content |
|---|---|
| [docs/task.pdf](docs/task.pdf) | The assignment brief |
| [docs/mvp-flows.md](docs/mvp-flows.md) | Every flow, decision and known limit (source of truth) |
| [docs/dashboard.md](docs/dashboard.md) | Dashboard screens and UX rules |
| [docs/on-prem.md](docs/on-prem.md) | Technology choices, Compose and Kubernetes runtime, log senders |
| [docs/research.md](docs/research.md) | Day 1 research plan |
| [apps/api/README.md](apps/api/README.md) | Back-end setup, CLI, worker, security limits |
| [apps/dashboard/README.md](apps/dashboard/README.md) | Dashboard setup, styling, file map |
