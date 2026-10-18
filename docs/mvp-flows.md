# MVP Flows (back end)

Source of truth for locked MVP flows. Build the system map and artifacts from this file.

- Architecture: research map F0–F6, locked 2026-10-16 (founder validated).
- Stack: Python 3.14 + uv + FastAPI + PostgreSQL. Code: `apps/api`. Full technology list and on-prem infrastructure: [on-prem.md](on-prem.md).
- Phase 1: back end, front end, database. Phase 2: infrastructure (later).
- Method: design each flow alone, then compose the system map at the end.
- Two deployment targets: on-prem (one customer) and managed (multi-tenant, one shared system). The flows are the same for both. Every table has `site_id`.

## Status

| Flow | Name | Status |
|---|---|---|
| S | Store (database) | LOCKED 2026-10-17 |
| 1 | Import logs | LOCKED 2026-10-16 |
| 1b | Pair CDN + origin logs | LOCKED 2026-10-16 |
| 2 | Verify identity | LOCKED 2026-10-16 |
| 3 | Classify (6 classes) | LOCKED 2026-10-16 |
| 4 | Activity reconstruction | LOCKED 2026-10-16 |
| 5 | Recommendation engine | LOCKED 2026-10-16 |
| 6 | Dashboard (API + UI) | DRAFT 2026-10-16 — see dashboard.md |
| 7 | Pipeline run / scheduler logic | LOCKED 2026-10-16 |

---

## Store · One PostgreSQL — LOCKED 2026-10-17

Question: "Do the high log volumes need a second database?" No. Upload and write speed are not the limit. The limit is how much data each run reads again (Flow 4), and a second database does not fix that.

### Size check (large site: 10 M log lines/day)

| Load | Size | Postgres? |
|---|---|---|
| Event writes | ~115 rows/s average, 1–2 k/s peak | Yes. `COPY` does > 100 k rows/s. |
| Storage | ~400 B/row + indexes ≈ 5–6 GB/day | Yes, with daily partitions. |
| View updates | Only open sessions + current hour (Flow 4) | Yes. Updates per minute ≤ events per minute. |

### Decisions

| # | Decision | Reason |
|---|---|---|
| S.1 | One PostgreSQL for all tables. No separate log database in the MVP. | Flow 7 needs transactions across `events`, `verdicts`, `import_files`. Two databases = no atomic write = extra reconciliation code. One fewer service inside a bank network. |
| S.2 | `events` partitioned by day (`RANGE` on `ts`). BRIN index on `ts`, B-tree on `client_key`. Retention = `DROP` old partition. | Cheap retention, no large `DELETE` + vacuum. |
| S.3 | All reads and writes of `events` and the views go through one store module. | A move to another store later changes one module. |
| S.4 | Workers write view rows in an append shape: "newest version of row X" (`session_id`, `version`, values). Postgres store = `INSERT … ON CONFLICT DO UPDATE`. | The same worker code works with an append-only store at scale. |
| S.5 | Scale path, only on a measured trigger: (1) bigger Postgres instance; (2) TimescaleDB compression on the same Postgres; (3) above ~1 B events/day: ClickHouse for `events` + views (`ReplacingMergeTree` keeps the newest version), Postgres keeps metadata, verdicts, runs. | Postgres while it is cheap and simple. S.3 + S.4 make the move one module. |
| S.6 | Unique constraint on `import_files.sha256`. | Two copies of one chunk (sender retry) can arrive at the same moment. The second insert fails → reply "already have it". |

---

## Flow 1 · Import logs — LOCKED 2026-10-16

Agents do not call our system. An agent calls the customer site, and the site writes a log line. Our system starts at the log file.

### Where the agent enters

```
 AI agent        Customer site         Sender                Our system
 (GPTBot…)       (nginx / CDN)         (Vector / CDN push)   (/ingest + worker)
    │  GET /pricing    │                     │                     │
    │─────────────────►│                     │                     │
    │  403             │                     │                     │
    │◄─────────────────│                     │                     │
    │                  │  write 1 log line   │                     │
    │                  │────────────────────►│                     │
    │                  │                     │ every 30 s / 10 MB: │
    │                  │                     │ POST gzip chunk     │
    │                  │                     │────────────────────►│ store file, 202
    │                  │                     │                     │ worker imports
    │                  │                     │                     │ on next tick (1 min)
```

### Delivery (who sends the logs)

The customer's systems send. We never fetch from their servers. Setup of the senders: [on-prem.md](on-prem.md).

```
 CDN ─────── vendor log push (batch every 30 s – 5 min) ──────────┐
 nginx ─► access.log ─► Vector agent (on each origin server) ─────┼──► POST /ingest ──► Inbox
 CDN that writes only to its own bucket ◄── our bucket reader ────┘    (S3-compatible)
 Dashboard upload · CLI (old logs) ───────────────────────────────┘
```

Delay request → dashboard: about 1–6 min. The CDN push batch sets the floor.

### Flow

```
 Auto delivery ─┐
 Dashboard ─────┼──► Inbox ──► Import job (every 1 min) ──► Store: events
 CLI ───────────┘     │        parse · validate · dedupe     (raw IP kept)
                      │                │                          │
                      │                ▼                          ▼
                      │        import_runs: status,         Flow 2 Verify
                      │        counts, rejects              reads from store
                      ▼
               Cleanup job (daily)
               deletes a file when status = success
               AND age > retention (7 days)
```

### Sequence

```
 Sender        /ingest (api)              Inbox (S3)     Store (Postgres)      Worker
   │ POST chunk     │                         │                │                  │
   │ + site token   │ check token, rate limit │                │                  │
   │───────────────►│ stream 64 KB parts ────►│                │                  │
   │                │ sha256 during stream    │                │                  │
   │                │ INSERT import_files (sha256 unique) ────►│                  │
   │                │   duplicate → delete object, 200         │                  │
   │◄── 202 ────────│                         │                │                  │
   │                │                         │                │◄── tick (1 min): │
   │                │                         │                │    files with    │
   │                │                         │                │    status = new  │
   │                │                         │◄── read file ──┼──────────────────│
   │                │                         │                │◄── parse, write  │
   │                │                         │                │    events,       │
   │                │                         │                │    last_seen     │
   │  no new data for 1 h from a source of a site → ALERT (names CDN or origin)   │
```

### Per-line processing

```
 raw line
    │
    ▼
 Adapter (origin · CDN) ── wrong shape ──► Rejects: line no. + reason
    │ fields
    ▼
 Validate (time, status, size limits) ── bad value ──► Rejects
    │
    ▼
 Dedupe (request ID) ── same key ──► count, skip
    │
    ▼
 Event record (Request + Client fields) ──► Store
```

### File lifecycle

```
 new ──► importing ──► success ──(after 7 days)──► deleted by cleanup job
                  └──► failed ──► file stays; fix the cause, then import again

 new / success / failed ──(Delete import)──► row, events and raw file removed; views rebuilt
```

### Decisions

| # | Decision | Reason |
|---|---|---|
| 1.1 | Three entry points: automatic log delivery (main), dashboard upload, CLI. All three put the file into the inbox. | One import path. |
| 1.2 | CLI `--now` imports at once, with the same code. | Demo, tests and handover must not wait for the scheduler. |
| 1.3 | A scheduled import job runs every 1 min (setting). The API does not start imports. | Logs arrive all the time. PDF §05: async ingest. The lock skips a tick while a run is active, so the real delay = run time. |
| 1.4 | Alert when a site sends no new data for 1 h (setting for each site). The alert names the source (CDN or origin). | PDF §05: "alert when data stops arriving". We cannot see a sender that stopped; this alert is the only signal. |
| 1.5 | The user selects the source type (origin log or CDN log) for each site. No auto-detect. | A wrong guess corrupts the data silently. F3: one source for each site. |
| 1.6 | Stream the file one line at a time. | The file size is not known. |
| 1.7 | Rejected lines: keep the line number and the reason, not the line text. | Hostile or malformed input (PDF §05). |
| 1.8 | Dedupe removes duplicate log lines only: file sha256 + line key. Line key = source request ID (if the source has one) + timestamp + method + path + status. A vendor request ID alone is not trusted as unique. Repeated agent requests are kept. | Repeated requests are retry and loop signals for activity reconstruction and the rules. |
| 1.9 | A "force import again" option bypasses the sha256 check. | Fix an adapter bug, then import the file again. |
| 1.10 | Raw files are kept. A daily cleanup job deletes them when status = success and age > retention (7 days). Failed files stay. | Recovery from parser bugs. |
| 1.11 | The import writes events directly to the store. Verify is a separate step that reads from the store. | No redaction in the MVP, so no in-memory-only constraint. Each step can run again alone. |
| 1.12 | No redaction in the MVP: no IP hashing and no query-string stripping. | Internal system (user decision 2026-10-16). Overrides F4 for the MVP. |
| 1.13 | Delivery = micro-batches pushed by the customer, not a per-line stream. Senders push gzip chunks every 30 s or 10 MB. | The CDN push sets the floor (30 s – 5 min). Pairing and the 30-min session gap wait anyway. A stream needs a broker, offsets and exactly-once logic. |
| 1.14 | The customer sends; we never fetch from their servers. CDN = vendor log push. Origin = Vector agent on each origin server, run by the customer; we supply `vector.toml`. Fluent Bit is also accepted. Vector sends raw lines; our importer is the only parser. | No SSH or credentials into customer hosts. Senders retry and buffer on disk. |
| 1.15 | One entry: `POST /ingest?site=<id>`, bearer token for each site. Body streamed to the inbox in 64 KB parts (not FastAPI `UploadFile`); sha256 calculated during the stream; insert `import_files` (status new); reply `202`. No parsing in the request. Body limit 50 MB. | The only method Vector `http` and CDN HTTP push support. Flat memory. A slow parser cannot block senders. |
| 1.16 | Rate limit and byte quota for each site at `/ingest`. Over the limit → `429`; the sender keeps the data on its disk and retries. | One tenant cannot flood the system. No data lost. |
| 1.17 | No presigned URLs for machine senders. A CDN that writes only to its own bucket → our bucket reader lists it every 1 min (read-only access) and copies new objects into the inbox. Dashboard upload: MVP = same streamed POST (limit 2 GB); later = presigned multipart. | Vector and CDN push cannot do the 2-step presigned flow. |
| 1.18 | `import_files.priority`: live (sender chunks) or backfill (dashboard upload, CLI of old logs). Backfill runs only when no live work waits. | A large upload of old logs must not delay the 1-min live data of other sites. |
| 1.19 | Inbox storage behind one interface, S3 API. | Same code for S3, the customer's S3-compatible storage and SeaweedFS. |
| 1.20 | Test data = log files committed in `samples/logs/`, loaded through the normal upload or CLI path. The file name holds site, source and start time (`<site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log[.gz]`). | Test data goes through the same parser and pipeline as customer data. A dropped file gives only its name, so the name carries site and source. |
| 1.21 | `DELETE /api/imports/{id}`: one transaction under the site's fast-lane lock (transaction-level advisory lock). It deletes the file's events (also paired rows that hold its origin lines), resets paired partner files to `new` so their own lines are read again, deletes the file row, then deletes all views of the site and sets `in_views = false` on its events. The raw file is deleted after the commit. Refused (`409`) during a run, during an import, or when a partner's raw file is gone. | A paired row holds lines of two files. The incremental views only add, so a full rebuild of the site is the only correct result after rows are removed. The freed sha256 lets the same file be loaded again. |

### Known limits / gaps (for the handover)

- Raw IPs and full URLs (with query strings) are stored. Redaction is necessary before customer use (PDF §05, §09).
- nginx logs have no request ID by default. When two files overlap in time, the same lines can be counted twice. The MVP warns the user when the time ranges of two files overlap.

---

## Flow 1b · Pair CDN + origin logs — LOCKED 2026-10-16

Change: F3 said "one source for each site". New decision (team, 2026-10-16): import both the CDN log and the origin log, and pair them by default.

Rule: provider-neutral. No CDN vendor name, header or field in the code or the data model (PDF §03.A, §05 Deployment). Vendor differences live only in config.

### Cases

```
 Case                     CDN log   Origin log   Result
 ──────────────────────── ───────── ──────────── ─────────────────────────────
 Blocked at edge          yes       no           CDN-only event (block)
 Served from CDN cache    yes       no           CDN-only event (cache hit)
 Forwarded to origin      yes       yes          PAIRED event (edge + origin status)
 Origin hit directly      no        yes          ORIGIN-ONLY event (CDN bypass: flag it)
```

### Client IP at the origin

```
 Agent 20.171.1.5 ──► CDN ──(X-Forwarded-For: 20.171.1.5)──► nginx
                                                              │ real_ip module,
                                                              │ trust CDN ranges only
                                                              ▼
                                         origin log: client IP = 20.171.1.5
```

### Pairing

```
 CDN log line ─────► edge_request_id ◄───── origin log line
   (CDN field map)    generic field         (nginx logs the forwarded
                      in our schema          request-ID header; header
                                             name = site setting)
                            │
                            ▼
        key: edge_request_id + method + path, time within ±N s
                            │
                            ▼
             one event: edge fields + origin fields
```

### Decisions

| # | Decision | Reason |
|---|---|---|
| 1b.1 | Pair CDN and origin logs by default. One request = one event. | Edge blocks and origin failures for the same request are both visible. |
| 1b.2 | nginx logs the real client IP from `X-Forwarded-For` (real_ip module). | Standard, works with any CDN. Without it, the origin log shows the CDN IP and Verify fails. |
| 1b.3 | real_ip trusts `X-Forwarded-For` only from the CDN IP ranges (`set_real_ip_from`). | Any client can send a false `X-Forwarded-For`. A spoofer could copy a bot IP and get VERIFIED. |
| 1b.4 | Schema has one generic field, `edge_request_id`. The CDN adapter reads it through a field map (YAML). The name of the request-ID header is a site setting. | No vendor in the code or data model. A new CDN = a new config file, not new code. |
| 1b.5 | Pair key = edge_request_id + method + path + time window. | A vendor request ID is not trusted as unique. |
| 1b.6 | Pair runs as a step after the import. Unpaired events wait for a time window, then stay single. | CDN and origin files arrive at different times and in any order. |
| 1b.7 | If a site has no request ID in both logs: no pairing. Use one source only (F3 rule: outermost hop). | Without a shared ID, two logs of one request give a double count. |

### Why the nginx ID cannot pair

Each layer writes its own log. Information goes only forward, in the request. The CDN log is written without the nginx ID.

```
 Agent            CDN layer                       Origin layer (nginx)
   │  GET /pricing   │                                 │
   │────────────────►│ makes its ID "E7"               │
   │                 │ request + header: E7            │
   │                 │────────────────────────────────►│ makes $request_id "N9"
   │                 │                                 │ origin log: E7, N9
   │                 │◄────────────────────────────────│
   │◄────────────────│ CDN log: E7                     │
 Shared value in both logs = E7 (CDN ID). N9 is in one log only.
```

### Field map (one YAML file for each supported CDN)

```yaml
# config/cdn/<vendor>.yaml   — vendor names live ONLY here
edge_request_id: <vendor log column with the request ID>
client_ip:       <vendor column>
path:            <vendor column>
status:          <vendor column>
origin_header:   <header the CDN sends to origin; customer logs it in nginx>
```

```
 vendor log line ──► CDN adapter ──reads──► <vendor>.yaml
                        ▼
 our event: edge_request_id · client_ip · path · status   (code knows only these)
```

- MVP: one field map, for the CDN in the demo data. Other vendors = add a YAML file, no code change.

### Required origin config (customer side, setup guide)

- nginx `real_ip` with `set_real_ip_from <CDN ranges>` and `real_ip_header X-Forwarded-For`.
- `log_format` includes the forwarded request-ID header of the site's CDN.

### Open

- The ±N s time window value (check on demo data).

---

## Flow 2 · Verify identity — LOCKED 2026-10-16

Question: "This client says it is bot X. Is that true?" Inputs: UA and client IP only. (The CDN bot score is a Classify input, Flow 3.)

### Data flow

```
 Store: events (no verdict)
    │
    ▼
 Group by client_key = (UA, client IP)    ← one check for each key, not each line
    │
    ▼
 Match UA to registry ── no bot name ──► UNKNOWN (not declared; no new method)
    │ claims "GPTBot"
    ▼
 Cache (key) ── hit ──► cached verdict
    │ miss
    ▼
 What does the vendor publish? (registry)
    ├─ IP list ─► IP in snapshot?  yes ► VERIFIED   no ► SPOOFED
    ├─ rDNS ────► reverse + forward match ► VERIFIED   no match ► SPOOFED
    │             lookup error / timeout ──────────────► UNVERIFIED
    └─ nothing ─────────────────────────────────────────► CLAIMED
    │
    ▼
 verdicts table: append-only rows per key; each event points to the row current at its time
```

### Example

```
 #  path        UA              IP            client_key
 1  /pricing    GPTBot/1.2      20.171.1.5    A
 2  /products   GPTBot/1.2      20.171.1.5    A
 3  /about      GPTBot/1.2      20.171.1.5    A
 4  /pricing    Googlebot/2.1   45.33.9.9     B
 5  /home       Chrome/129      81.2.3.4      C

 clients table
 key  claimed    verdict    method    evidence
 A    GPTBot     VERIFIED   ip_list   "in vendor list, snapshot 2026-10-10"
 B    Googlebot  SPOOFED    rdns      "45.33.9.9 → host.linode.com"
 C    —          UNKNOWN    none      "no bot name in UA"
```

### Sequence (rDNS case)

```
 Verify job          Cache            DNS resolver
    │ (Googlebot, 66.249.66.1)?           │
    │─────────────────►│                   │
    │ miss             │                   │
    │◄─────────────────│                   │
    │ PTR 66.249.66.1                      │
    │─────────────────────────────────────►│
    │ crawl-66-249-66-1.googlebot.com      │
    │◄─────────────────────────────────────│
    │ A crawl-66-249-66-1.googlebot.com    │
    │─────────────────────────────────────►│
    │ 66.249.66.1 (same IP → match)        │
    │◄─────────────────────────────────────│
    │ save VERIFIED, 24 h                  │
    │─────────────────►│                   │
```

### Registry entry (data, not code)

```yaml
- id: gptbot
  vendor: OpenAI
  ua_pattern: "GPTBot"
  category: ai_crawler
  verify: { method: ip_list, source: openai-gptbot.json, snapshot: 2026-10-10 }
- id: googlebot
  vendor: Google
  ua_pattern: "Googlebot"
  category: search_crawler
  verify: { method: rdns, suffixes: [googlebot.com, google.com] }
```

### Decisions

| # | Decision | Reason |
|---|---|---|
| 2.1 | Runs as a step after import + pair in each scheduler run. Processes only events with no verdict. | Same pattern as Flow 1. Can run again alone. |
| 2.2 | client_key = (UA, client IP). One check for each key while inputs do not change. Results in an append-only `verdicts` table; events point to a verdict row (N : 1). | Millions of lines, thousands of clients. DNS calls are slow. |
| 2.3 | Client IP comes from the CDN log line (paired events) or the real_ip value in the origin log. | The CDN IP would give a false SPOOFED. |
| 2.4 | Method = what the vendor publishes: IP list first (offline, fast), then rDNS. | F1. A UA is a claim (PDF §02). |
| 2.5 | No signature check (RFC 9421) in the MVP. | Default logs do not contain signature headers. |
| 2.6 | DNS error or timeout = UNVERIFIED, not SPOOFED. | A failed check is not proof of a lie. |
| 2.7 | Not declared and not classifiable = UNKNOWN. No new detection method. | Founder decision: undeclared bots are an unsolved problem; be honest. |
| 2.8 | Append-only verdicts: each check ADDS a verdict row (client_key, verdict, versions, checked_at). Never upsert or overwrite. Each event points to the verdict row that was current at its time. | Analytics must keep history. A verdict that was true on Monday stays true for Monday's events (PDF §05 auditability). |
| 2.8a | Same key, inputs unchanged → reuse the current verdict row (no new row). Check again (new row) only when: IP-list snapshot version changes, registry or rule version changes, or rDNS result older than 24 h. | Same inputs give the same answer. rDNS is a slow network call. |
| 2.8b | Scheduler downloads vendor IP lists one time each day (new snapshot version). | A stale list keeps a stale verdict forever. |
| 2.9 | Each row stores verdict, method, evidence text, registry version, checked_at. | PDF §05 auditability. |
| 2.10 | Registry = YAML files built from arcjet/well-known-bots and ai.robots.txt. | PDF §03.B: a new bot must not change pipeline code. |

### Known limits

- IP lists change over time. MVP uses the latest snapshot and writes its date in the evidence, so a wrong SPOOFED on an old log is visible. Matching each event to the snapshot of its own date = later.
- Bots that publish no method stay CLAIMED. Undeclared bots stay UNKNOWN.

---

## Flow 3 · Classify — LOCKED 2026-10-16

Question: "Which of the 6 PDF classes is this client in?" Deterministic rules. No ML (PDF: "skip the ML"). Output = the 6 top-level classes only, no subtypes.

### Inputs (for each client)

| Input | From |
|---|---|
| Verdict (VERIFIED / CLAIMED / UNVERIFIED / SPOOFED / UNKNOWN) | Flow 2 |
| Registry category (search crawler, AI crawler, agent client, other bot, automation tool) | Registry |
| UA type (browser, headless, library such as python-requests) | UA parser |
| Edge bot signal (bot / human / none) | CDN log via field map, if the CDN has one |

### Rules (in order; the first match wins)

```
 client
   ├─ SPOOFED? ───────────────────────────────► 6 UNKNOWN (flag: spoofed)
   ├─ search crawler?
   │     ├─ VERIFIED ─────────────────────────► 1 VERIFIED SEARCH CRAWLER
   │     └─ CLAIMED / UNVERIFIED ─────────────► 3 OTHER IDENTIFIABLE BOT
   │                                             "claims Googlebot, unverified"
   ├─ AI crawler or agent client? ────────────► 2 KNOWN AI CRAWLER (confidence = verdict)
   ├─ other bot / library UA? ────────────────► 3 OTHER IDENTIFIABLE BOT
   ├─ headless UA, or edge = bot + browser UA ► 4 BROWSER AUTOMATION / AGENT-LIKE
   ├─ browser UA + edge = human ──────────────► 5 ORDINARY BROWSER
   └─ anything else (incl. browser UA, no edge signal) ► 6 UNKNOWN
```

### Confidence

```
 VERIFIED ───────────────► High
 CLAIMED / edge signal ──► Medium
 UNVERIFIED / UA only ───► Low
```

### Decisions

| # | Decision | Reason |
|---|---|---|
| 3.1 | Classify one time for each (client_key, edge bot signal). | The key must contain every rule input. The edge signal has 3 values only. |
| 3.2 | The CDN field map converts the vendor bot score to bot / human / none. The threshold is in the YAML file. | Vendors use different scales. Code stays neutral. |
| 3.3 | Bot names = YAML data. Rule order = code, with `rule_version`. | PDF §03.B: new bot = no code change. Logic stays testable. |
| 3.4 | Class, confidence, rule ID, rule version and evidence are stored on the same append-only verdict row as Flow 2 (decision 2.8). No overwrite. | PDF §05 auditability. History is kept. |
| 3.5 | Agent clients (for example ChatGPT-User) → class 2. | They declare themselves. Class 4 is for activity found only from evidence. |
| 3.6 | Browser UA with no edge signal → class 6 UNKNOWN, not class 5. Dashboard text: "browser UA, not confirmed human". | A UA is a claim. Founder rule: be honest. |
| 3.7 | No subtypes in the output. Activity reconstruction reads the registry category (agent client) for the 2-min session gap. | 6 classes are enough. The category is already registry data. |

### Known limits

- On a site with origin logs only, almost all human traffic is UNKNOWN.
- Undeclared bots that look like browsers are UNKNOWN unless the CDN gives a bot signal.

### Verdict rows: three cases (Flows 2 + 3)

```
 New event (UA, IP)
   ├─ no row for key ─────────────────────────────► check → ADD row #1
   ├─ row exists, inputs unchanged ───────────────► REUSE current row (no new row)
   └─ row exists, an input changed ───────────────► check again → ADD row #2
      (new IP-list snapshot · new registry/rule      (row #1 stays; old events
       version · rDNS older than 24 h)                 keep pointing to it)

 Mon  GPTBot 20.171.1.5 → row #1 VERIFIED (snapshot Mon) ◄── events 1–40
 Tue  new snapshot without the IP
      GPTBot 20.171.1.5 → row #2 SPOOFED  (snapshot Tue) ◄── events 41–60
```

---

## Flow 4 · Activity reconstruction — LOCKED 2026-10-16

Question: "What did each client do, in what order, and where does the evidence stop?" Implements F5.

### Keys

```
 Key               Used in    What it joins
 ───────────────── ────────── ──────────────────────────────────────────
 edge_request_id   Flow 1b    CDN line + origin line → 1 event (1 request)
 client_key        Flows 2–4  all events of one (UA, IP) → "who"
 verdict row       Flows 2–3  the label for "who" at a time
 session_id        Flow 4     "who" + "one visit" → "who, when"
```

Group by client_key + time, not by verdict row. A verdict covers many visits and can change during one visit.

### Data flow

```
 events + verdicts (append-only)
        │
        ▼
 1 TAG ◄── site_config.yaml (key pages · conversion pages · journeys)
        ▼
 2 SAME CLIENT?  client_key (UA + IP; IPv6 → /64) · no UA/IP ──► NOT GROUPED
        ▼
 3 SAME VISIT?   gap > 30 min (agent clients: 2 min) = new session
        ▼
 4 SESSION FACTS ──► V1 Session
        ▼
 5 GROUP-BYS ──► V2 Agent · V3 Page / Journey
```

### Why a session row changes after it is first written

Logs arrive in 1-min batches. A visit is longer than 1 min. So the same visit is seen over several runs.

```
 run 10:01   sees /pricing, /docs/api        ──► session #812: 2 pages, no failure          (open)
 run 10:02   sees /signup 403 ×3             ──► session #812: 3 pages, blocked, 3 retries  (open, same row)
 10:32+      no request for 30 min           ──► session #812 closed: final, never changes
```

The dashboard (Sessions list) and rules P1 / P3 need the visit as one story, not single lines.

### How the views are kept current

```
 new events ──► worker (for one site)
                  ├─ session still active (last event < 30 min + delivery margin) ──► open_sessions   upsert each run
                  └─ session idle ─────────────────────────────────────────────────► sessions        append once, never changed
 page_stats · agents · journey_steps ──► one row for each hour: only the current hour's rows change
 dashboard ──► reads sessions + open_sessions ("in progress" label on open rows)
```

| Table | Rows changed in each run | Write |
|---|---|---|
| `sessions` (closed visits, almost all rows) | 0 | Append only |
| `open_sessions` (current visits) | A few thousand for a large site | Upsert; moved to `sessions` when the visit closes |
| `page_stats`, `agents`, `journey_steps` | Current hour only | Upsert of hourly rows. The dashboard adds up the hours. Distinct counts (clients, sessions) come from the session tables, not from adding hours. |

Each new event changes at most one open session, so updates per minute ≤ events per minute. Cost grows with active visits, not with history. All rows have `site_id`.

### How (SQL in the store)

- **V1 Session:** window functions. `LAG(ts) OVER (PARTITION BY client_key ORDER BY ts)`; new session when gap > limit; running `SUM` of "new" flags = session_no; `GROUP BY client_key, session_no`. Retry / loop flags = `LAG` on path + status in the same query.
- **V2 Agent:** `GROUP BY claimed_agent` over V1 + events (PDF "Agent directory"). Clients with no bot name: one row for each class, e.g. "Unknown (browser UA)".
- **V3 Page:** `GROUP BY path, class`: requests, distinct clients, status mix, error rate, block rate (403/429), retries, key-page tag. Key pages never reached = `LEFT JOIN` site-config list → requests = 0.
- **V3 Journey:** per session, highest step reached of each site-config journey; then `GROUP BY journey, class`.

```
 client A:  10:00 10:01 10:03 ──(90 min)── 11:33 11:34
 new?        1     0     0                  1     0
 running SUM 1     1     1                  2     2   → session 1, session 2
```

### Tables (kept current each run; the rule queries in Flow 5 run on these)

```
 sessions          one row = one closed visit (open_sessions: same columns, visits still active)
   session_id · client_key · verdict_id · claimed_agent · class · confidence · started ·
   last_seen · requests · distinct_pages · pages_in_order[] · key_pages_visited ·
   reached_conversion · has_retry · has_loop · gaps[]
 session_events    one row = one event inside one visit (drill-down to evidence, PDF §03.D)
   session_id · event_id · seq
 page_stats        one row = one path × one class (V3 page)
   path · class · tags[] · requests · sessions · median_bytes ·
   n_2xx · n_3xx · n_403 · n_429 · n_4xx · n_5xx · retries
 journey_steps     one row = one step of one journey × one class (V3 journey)
   journey_id · class · step_no · step_path · sessions_reached · sessions_retry_or_loop
 agents            one row = one claimed identity (V2)
   claimed_agent · class · verification · first_seen · last_seen · requests ·
   sessions · distinct_pages · top_paths[]
```

### Labels

```
 Observed  counts, order, status codes, times
 Inferred  grouping into a session, confidence
 Unknown   outcome, intent, gaps
```

### Session confidence

```
 High    VERIFIED + IP not shared
 Medium  CLAIMED or browser, IP not shared
 Low     agent client, shared IP, or UNKNOWN class
```

### Decisions

| # | Decision | Reason |
|---|---|---|
| 4.1 | Closed sessions are appended once; only `open_sessions` and the current hour's rows of the other views are upserted, for the site with new events. Views are still derived; history lives in events + verdicts. | A full rebuild reads all history every run and grows with every site and day. Open/closed keeps almost all writes as appends. |
| 4.5 | A session closes when its last event is older than the gap (30 min, agent clients 2 min) plus a delivery margin for late CDN files. | Late files can still add to a visit that looks finished. |
| 4.6 | Late events for an already closed range (backfill, very late file): re-compute that client's sessions in that time range, delete + insert in one transaction. Rare path. | Keeps closed rows correct without a full rebuild. |
| 4.7 | Upserts and deletes for one site run in one transaction. Readers see the old rows or the new rows, never a mix (Postgres MVCC). No table swap, no exclusive lock. | Safe for many sites in one table. Dashboard reads never wait. |
| 4.2 | Retry = same client + same path again within 60 s after 4xx/5xx. Loop = redirect back to a visited path, or same path ≥ 5 times. Values in config. | Facts for the rules. Reconstruction reports, rules judge. |
| 4.3 | Shared-IP flag (CGN 100.64/10, cloud-egress ranges in registry) lowers confidence. | Same IP ≠ same agent (PDF §03.C). |
| 4.4 | Each session lists its gaps ("no CDN log: edge blocks unknown", "outcome unknown"). | PDF §03.C. |

### Known limits

- Frequent upserts on `open_sessions` and the hourly rows leave dead row versions. Tune autovacuum for these tables.

---

## Flow 5 · Recommendation engine — LOCKED 2026-10-16

Question: "Which journeys should Webzero test next, and why?" Rules find and score candidates (SQL on Flow 4 tables). An LLM writes the text. Code owns every fact.

### Schedule

- Production: one recommendation run every 2 weeks, on the last 14 days of data. Not real-time, not eager.
- MVP: window = 6 hours (`--window 6h`). Run every 6 h, plus on demand (CLI command / button) for demo and tests.
- Views (Flow 4) still update after each import, for the dashboard. Recommendations are a separate command: `run-recommendations --window 14d`.

### Funnel (why the LLM never sees the millions)

```
 ~5,000,000 log lines ─► events ─► ~200,000 sessions ─► views (SQL)
        ─► 5 pattern queries ─► ~20 candidates ◄── LLM works ONLY here
```

### Data flow

```
 sessions · page_stats · journey_steps · agents ──┐
 site_config (key/conversion pages, journeys) ────┤
 access policy (robots.txt + allow/block) ────────┤
 site_pages (customer sitemap / content list) ────┘
        ▼
 1 PATTERN QUERIES (one SQL each) ─► 2 CANDIDATES (pattern · target · session IDs · counts)
        ▼
 3 SCORE = Impact × Frequency × Severity × Confidence        (code)
        ▼
 4 FACT BUNDLE (SQL, exact)                                  (code)
        ▼
 5 LLM writes 4 text fields ─► VALIDATOR ─ pass ─► text
                                         └ fail / LLM off ─► template text (fallback)
        ▼
 6 RANKED LIST, stored as one run (append-only)
```

### Step 1: Patterns (PDF §04)

```
 Pattern              Query (on Flow 4 tables)                                  Target
 ──────────────────── ───────────────────────────────────────────────────────── ───────────
 P1 Product discovery sessions: class 2/4, key_pages_visited ≥ 3, NOT           product→conv.
                      reached_conversion
 P2 Blocked access    page_stats: class 1/2, key page, access policy ALLOWS,    page
                      n_403 + n_429 ≥ 5   (blocked by intent = skip)
 P3 Broken navigation journey_steps: sessions_retry_or_loop ≥ 3                 journey step
 P4 Content discov.   site_pages (key content) LEFT JOIN page_stats (class 2):  URL
                      never fetched · fetched but 403/3xx to login ·
                      200 with bytes far below browser median (Inferred)
 P5 Full journey      journey_steps: critical journey, step 1 reached,          journey
                      end not visible in logs
```

Evidence for all: query → session IDs → session_events → events (exact log lines).

### Step 3: Score (each factor visible in UI)

```
 Impact     key / conversion page = 3 · other = 1           (site_config)
 Frequency  sessions affected: < 5 = 1 · 5–50 = 2 · > 50 = 3
 Severity   P2, P3 = 3 · P1, P4, P5 = 2                      (fixed per pattern)
 Confidence most evidence sessions: High 1.0 · Medium 0.6 · Low 0.3
 Example: P2 on /pricing = 3 × 2 × 3 × 1.0 = 18
```

### Step 4: Fact bundle (what the LLM reads)

```
 · status for each class on the target (e.g. AI crawlers 403 · browsers 200)
 · which agents + verification       · when (time pattern)
 · access policy for the path        · journey position
 · related candidates (same journey) · up to 5 sample events (with IDs)
```

### Step 5: Who fills which field

```
 Field                 Filled by
 ───────────────────── ────────────────────────────────
 Recommended test      code (target + journey)
 Reason                LLM (from bundle)
 Evidence              code (links to sessions/events)
 Potential issue       LLM (label: Inferred)
 Suggested validation  LLM
 Priority              code (score + factors)
 Confidence            code
 Next action           LLM (must state the Unknown part and why simulation is needed)
```

### Decisions

| # | Decision | Reason |
|---|---|---|
| 5.1 | All 5 patterns. P4 = customer sitemap / content list vs fetches. No page-content check, no fetching pages. | We capture, we do not diagnose content. |
| 5.2 | Thresholds (3 pages, 5 × 403, 3 sessions) and frequency buckets in config, set for each window size. | A 6 h window has far fewer sessions than 14 days. Tune on demo data. |
| 5.3 | Inputs: site_config (written by a person), access policy, site_pages (sitemap). | Logs cannot tell which pages matter or which blocks are intended. |
| 5.4 | Append-only runs with rule_version. Stable ID = hash(pattern, target). UI shows new / still open / gone vs the previous run. | History rule: evidence stays valid after a PM acts. |
| 5.5 | Production: every 2 weeks, 14-day window. MVP: 6-hour window, every 6 h + on demand. Window is a setting. Each run is stored. | Not real-time or eager (team decision 2026-10-16). |
| 5.6 | Each recommendation states its Unknown part and why simulation is needed. | PDF §04. |
| 5.7 | LLM writes only Reason, Potential issue, Suggested validation, Next action. Code fills the rest. | Facts can never be invented. Long-term: richer, case-specific text than templates. |
| 5.8 | Validator: every number, path and agent name in the LLM text must be in the bundle. Fail → template text. | Catch hallucinations. |
| 5.9 | Template text = fallback when the LLM is off or fails. Build templates first (Day 4), LLM layer after. | Win condition never depends on the LLM. |
| 5.10 | Cache LLM text by hash(bundle). Store model + prompt version with the text. | Same facts → same text, low cost, auditability. |

### Out of scope

- AI page-content check, AI site-config suggestion.

### Roadmap

- LLM reads the ~50 most common journey shapes (SQL) and proposes new patterns.

---

## Flow 7 · Pipeline run (scheduler logic) — LOCKED 2026-10-16

Question: "How does one run work, and what happens when a step fails?" The trigger (cron / timer) is phase 2 infrastructure. The back end exposes commands only.

### Real-time context (PDF)

- The PDF never asks for real-time. §03.A: file import "misses real-time data". §05: "ingest asynchronously", "alert when data stops arriving". §08: Day 2 classified observations, Day 3 UI on real events.
- Floor = customer log delivery (CDN push batch, Vector flush). "Real-time" here = near real-time, about 1–6 min after the request.
- Sessions with last event < 30 min ago are labelled "in progress" (can still grow). Older = "closed".

### Two lanes

```
 FAST LANE: run-pipeline fast (every 1 min)       SLOW LANE: run-pipeline slow
 ──────────────────────────────────────────       ───────────────────────────────
 1 Import → 1b Pair → 2 Verify → 3 Classify       Recommendations (Flow 5)
 → 4 Views                                        MVP: every 6 h, 6 h window
 user sees: events, verdicts, classes,            + "Generate now" button / CLI
 sessions, agents, pages, journeys, counts,       Production: every 2 weeks, 14 d
 trends, import status, alerts
```

Steps run in order, one after another (each needs the output of the step before). Steps 1–3 process new work only; step 4 updates open sessions and the current hour (Flow 4).

Backfill (old logs from upload or CLI, decision 1.18) uses the fast-lane steps at low priority: a worker takes it only when no live work waits.

### Workers and the work line

No queue product. The `import_files` table is the queue: the file is in the inbox, its row says "not done", a crash leaves it "not done", and the count of waiting rows drives scaling.

```
 worker 1..N (same image; scale on "files waiting")
   loop:
     SELECT site_id FROM site_work
      WHERE work is due AND site not locked
      ORDER BY last_run_at              ◄─ waited longest = first (fair turns)
      FOR UPDATE SKIP LOCKED LIMIT 1    ◄─ two workers never take the same site
     lock this site + lane ─► run the lane for this site only
       work limit per run: 200 MB or 2 M lines; the rest = next turn
     release ─► next site

 site A ── lock A ── worker 1 ┐
 site B ── lock B ── worker 2 ├─ in parallel; one site never runs twice at once
 site C ── lock C ── worker 3 ┘
```

### One run (one site, one lane)

```
 worker loop  or  CLI / button
        ▼
 run-pipeline fast --site <id>
        ▼
 take SITE LOCK (site + lane) ── taken? ──► skip this site this tick (do not queue)
        ▼
 1 Import ─► 1b Pair ─► 2 Verify ─► 3 Classify ─► 4 Views
   each step = one transaction: all writes or none
        ├─ all OK ──► run = success · last_success = now
        └─ step N fails ──► stop; later steps do not run
                            run = failed (step, error); earlier steps keep their writes
        ▼
 release lock
```

### All locks

| # | Lock | Scope | Purpose |
|---|---|---|---|
| L1 | Site lock (Postgres advisory lock) | One site + lane | Sites run in parallel; one site never twice at once. |
| L2 | Step transaction | One step | No half-written step. Next tick = retry. |
| L3 | View-row transaction (Flow 4, 4.7) | One site's view rows | Readers see old or new rows, never a mix. |
| L4 | Unique `import_files.sha256` (S.6) | One file | Two copies of one chunk cannot both import. |

### "Not done yet" (why a failed run is safe to repeat)

```
 Step       "not done yet" means
 ────────── ─────────────────────────────────────
 Import     file status ≠ success
 Pair       event not paired, wait window not over
 Verify     client key with no current verdict
 Classify   verdict row with no class
 Views      open sessions + current hour of a site with new events
```

No special retry code: the next tick is the retry.

### Failure vs not a failure

```
 NOT a failure (handled inside the step)        A failure (stops the run)
 ─────────────────────────────────────────      ───────────────────────────────
 bad line     → rejects (Flow 1)                database error
 bad file     → file failed, others continue    bug / exception in code
 DNS timeout  → UNVERIFIED (Flow 2)             disk full
 LLM error    → template text (Flow 5)
```

### View update

```
 BEGIN
   upsert open_sessions, current-hour rows        (site A only)
   move closed visits ─► sessions (append)
 COMMIT ──► dashboard sees the new rows
   └─ fail ──► ROLLBACK; old rows stay; dashboard shows old data
```

Why not build new tables and swap them: one table holds many sites, so a swap rebuilds every site; the rename needs an exclusive lock that waits behind slow dashboard reads and blocks all new reads; indexes, grants and Postgres views attached to the old table are lost.

### What the user sees

```
 pipeline_runs: run_id · lane · started · finished · status · failed_step · error · counts

 Banner:  all OK              → "Data up to 14:05"
          last run failed     → "Data up to 13:55 · last run failed at Verify"
          3 failures in a row → ALERT (plus "no data for 1 h" alert from Flow 1)
```

### Decisions

| # | Decision | Reason |
|---|---|---|
| 7.1 | Two commands: `run-pipeline fast` (steps 1–4), `run-pipeline slow` (recommendations), each for one site. Trigger = a loop inside the worker process; the CLI stays for manual runs. | Back end owns logic. A loop needs no extra service and has no container start delay at a 1-min tick. |
| 7.2 | One lock for each site + lane (L1). Lock taken → skip that site this tick. | Postgres allows many writers. A global lock would make all sites wait for the largest one. |
| 7.3 | A failed step stops the run. Earlier steps keep their writes. | Later steps need complete input. |
| 7.4 | Each step = one transaction, "not done yet" work only. | Next tick = retry. |
| 7.5 | View rows of one site are updated in one transaction (L3, Flow 4 decision 4.7). | Dashboard never shows half-built data, and reads never wait. |
| 7.6 | Alert after 3 failed runs in a row. `/health` returns last success of each lane; > 15 min = unhealthy. | PDF §05 health checks + error logging. Phase 2 uses `/health`. |
| 7.7 | Sessions with last event < 30 min ago = "in progress". | Honest label: a later import can change them. |
| 7.8 | No queue product (SQS, Kafka). `import_files` + `FOR UPDATE SKIP LOCKED` is the queue. Add one only on a measured need: job polling loads the database, seconds-level delay is required, or other systems must react to new files. | A second list of work must be kept in agreement with the table. Load is ~7 requests/s; Postgres handles thousands. |
| 7.9 | N workers, same image. Fair turns: the site that waited longest goes first. Work limit per run: 200 MB or 2 M lines. | One large site cannot block the others. |
| 7.10 | Cap workers to fit the database connection limit. | Upload is not the bottleneck; processing is, and in processing the database is the shared limit. More workers help parsing; Flow 4 (4.1) keeps database work small. |
| 7.11 | `/health` and the "> 15 min = unhealthy" rule apply for each site and lane. | Many sites in one system. |
