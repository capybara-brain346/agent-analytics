# Ingestion

Ingestion moves log files from the customer into the `events` table.
Input: gzip or plain log chunks (push, upload, CLI, customer bucket). Output: rows in `events` (raw IP kept), file state in `import_files`, rejected lines in `import_rejects`.

Agents do not call this system. An agent calls the customer site, and the site writes a log line. This system starts at the log file.

## Read this when

- You change how log files arrive: `POST /ingest`, `POST /api/imports/upload`, the CLI `import` command or the bucket reader.
- You change token, rate limit or byte quota rules of `/ingest`.
- You change how a log line is parsed, validated, rejected or deduplicated.
- You add a CDN log field map or a new log format (the pairing module owns the pair logic).
- You change the file states, retries, resume offsets or the retention of raw files.
- You change `DELETE /api/imports/{id}` or the force re-import.
- You change the sample log file name rule.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/routes/ingest.py` | `POST /ingest` (sender push). Token, rate limit, quota, then `store_body`. Shared helpers `load_site`, `source_for`, `store_body`, `inbox_dependency`. |
| `apps/api/src/routes/imports.py` | `GET /api/imports`, `POST /api/imports/upload`, `DELETE /api/imports/{file_id}`. |
| `apps/api/src/services/ingest/service.py` | `accept_chunk`, `object_key`, `check_site_token`, `check_rate_limit`, `record_bytes`, `resolve_source`. In-process rate windows. |
| `apps/api/src/services/ingest/README.md` | Short guide of the ingest service. |
| `apps/api/src/services/importer/service.py` | `import_due_files` (pipeline step `import`), `import_local_file` (CLI). Claim, slice, parse, batch, retry. |
| `apps/api/src/services/importer/adapters/origin.py` | nginx "combined" log parser. |
| `apps/api/src/services/importer/adapters/cdn.py` | CDN JSON, CSV and TSV parser. Reads field maps from `config/cdn/`. |
| `apps/api/src/services/importer/adapters/common.py` | Shared validation and length caps. `validate()` returns `ParsedLine` or `Reject`. |
| `apps/api/src/services/importer/adapters/__init__.py` | `ParsedLine` and `Reject` data classes. |
| `apps/api/src/services/importer/adapters/README.md` | Short guide of the adapters. |
| `apps/api/src/services/importer/dedupe.py` | `line_key(line)`: stable hash of a line. |
| `apps/api/src/services/importer/bucket_reader.py` | `BucketReader`, `BucketTarget`, `targets_from_site_files`: copy new objects from a customer bucket. |
| `apps/api/src/services/importer/delete.py` | `delete_import`, `DeleteBlocked`, `ImportNotFound`. |
| `apps/api/src/services/importer/log_names.py` | `parse_log_name`, `is_log_file`, `LogName`: file name rule. |
| `apps/api/src/services/importer/README.md` | Short guide of the importer. |
| `apps/api/src/services/site_config/service.py` | `load_site_config`, `load_cdn_field_map`, `token_matches`, `CdnBucket`. |
| `apps/api/src/store/import_files.py` | `import_files`, `import_rejects`, `bucket_objects` access. File state machine. |
| `apps/api/src/store/inbox.py` | `Inbox` interface and `S3Inbox`: put stream, read lines, gunzip, list, copy, delete. |
| `apps/api/src/store/events.py` | `copy_events` (bulk insert and dedupe), `ensure_partitions`, `delete_file_events`, `delete_file_rows`, `drop_old_partitions`. |
| `apps/api/src/store/quota.py` | `bytes_received_last_day`: byte quota of `/ingest`. |
| `apps/api/src/config/settings.py` | All settings in this module (see Configuration). |
| `apps/api/config/cdn/example.yaml` | Template CDN field map. |
| `apps/api/config/cdn/cloudflare.yaml` | Field map of a Cloudflare Pages access log (a supported input, not a dependency). |
| `apps/api/config/sites/<site_id>.yaml` | Per site: `sources`, `cdn_field_map`, `request_id_header`, `ingest_token_sha256`, `no_data_alert_minutes`, `cdn_bucket`. |
| `apps/api/migrations/versions/0001_initial.py` | Tables `import_files`, `import_rejects`, `events` (unique index `events_dedupe`). |
| `apps/api/migrations/versions/0003_import_fixes.py` | Columns `import_files.lines_done`, `import_files.retries`. Table `bucket_objects`. |
| `apps/dashboard/src/lib/log-name.ts` | Dashboard copy of the file name rule. Keep it equal to `log_names.py`. |
| `deploy/vector/vector.toml` | Origin log sender config. Owned by [deployment](../deployment/README.md). |
| `samples/logs/README.md` | Sample log files and the file name rule. |
| `apps/api/tests/importer/`, `apps/api/tests/ingest/` | Tests of this module. |

## Data flow

Delivery paths (the customer sends; the system never fetches from customer servers, except the bucket reader):

```
 CDN ─────── vendor log push (batch, 30 s - 5 min) ───────────────┐
 nginx ─► access.log ─► Vector (on each origin server) ───────────┼─► POST /ingest ──► Inbox (S3)
 CDN that writes only to its own bucket ◄── bucket reader (worker) ┘   (site token)
 Dashboard upload ─► POST /api/imports/upload ────────────────────────────────────────► Inbox (S3)
 CLI (old logs, tests) ─► import_local_file ──────────────────────────────────────────► Inbox (S3)
```

Overview of the import:

```
 Auto delivery ─┐
 Dashboard ─────┼──► Inbox ──► import_files (new) ──► import_due_files (every tick) ──► events
 CLI ───────────┘                                      claim · stream · parse            (raw IP kept)
                                                       validate · dedupe                     │
                                                              │                              ▼
                                                              ▼                         Pairing, then
                                                    import_rejects (line no. + reason)  Verify (read from store)

 Cleanup (daily, pipeline module): success AND age > RAW_RETENTION_DAYS ─► delete inbox object
```

Sequence of a push:

```
 Sender        /ingest (api)               Inbox (S3)     Postgres            Worker
   │ POST chunk     │                          │              │                  │
   │ + site token   │ check token              │              │                  │
   │───────────────►│ rate limit, byte quota   │              │                  │
   │                │ stream body ────────────►│              │                  │
   │                │ sha256 during stream     │              │                  │
   │                │ INSERT import_files (unique site_id + sha256) ►│           │
   │                │   duplicate: delete object, reply 200          │           │
   │◄── 202 ────────│                          │              │                  │
   │                │                          │              │◄── tick:         │
   │                │                          │              │    claim file    │
   │                │                          │◄── read lines┼──────────────────│
   │                │                          │              │◄── COPY events,  │
   │                │                          │              │    rejects, state│
```

Per-line processing:

```
 raw line
    │
    ▼
 Adapter (origin or CDN) ── wrong shape ──► import_rejects: line no. + reason
    │ fields
    ▼
 Validate (time, status, size limits, future time) ── bad value ──► import_rejects
    │
    ▼
 Dedupe (line_key, unique index events_dedupe) ── same key ──► count as duplicate, skip
    │
    ▼
 Event row (Request + Client fields, pair_state) ──► events
```

File lifecycle:

```
 new ──► importing ──► success ──(RAW_RETENTION_DAYS, cleanup)──► row stays, object deleted
   ▲        │  └─────► failed ──► row and object stay; fix the cause, then force re-import
   │        │
   └────────┘ work limit reached (resume offset lines_done) or transient error (retries)

 new / success / failed ──(Delete import)──► row, events and raw object removed; views rebuilt
```

Time from request to dashboard: about 1 to 6 minutes. The CDN push batch sets the floor.

## Rules and decisions

Decision IDs keep the numbers of the original design.

| ID | Rule | Why |
|---|---|---|
| [1.1] | Three entry points: automatic log delivery (main), dashboard upload, CLI. All three put the file into the inbox. | One import path. |
| [1.2] | CLI `--now` imports at once, with the same code. | Demo, tests and handover must not wait for the scheduler. |
| [1.3] | A scheduled import job runs every tick (`TICK_SECONDS`, 60 s). The API does not start imports. The lane lock skips a tick while a run is active, so the real delay equals the run time. | Logs arrive all the time. Async ingest. |
| [1.4] | Alert when a site sends no new data for `no_data_alert_minutes` (default 60, site setting). The alert names the source (CDN or origin). Only `live` files count. A source that never sent a file raises no alert. | We cannot see a sender that stopped. This alert is the only signal. A backfill upload must not hide a stopped sender. |
| [1.5] | The user selects the source type (origin or CDN) for each site. No auto-detect. | A wrong guess corrupts the data silently. |
| [1.6] | Stream the file one line at a time. Memory stays bounded (see Known limits for the caps). | The file size is not known. |
| [1.7] | Rejected lines: keep the line number and the reason, not the line text. At most `MAX_REJECTS_PER_FILE` (10,000) rejects for each file. Reason is cut to `MAX_REASON_CHARS` (200). | Hostile or malformed input. |
| [1.8] | Dedupe removes duplicate log lines only. Key = `line_key()`. Repeated agent requests are kept. A vendor request ID alone is not trusted as unique. | Repeated requests are retry and loop signals for activity reconstruction and the rules. |
| [1.9] | "Force import again" bypasses the sha256 check (`import_local_file(force=True)`, CLI `--force`). | Fix an adapter bug, then import the file again. |
| [1.10] | Raw files are kept. A daily cleanup job deletes the object when status = `success` and age > `RAW_RETENTION_DAYS` (7). The row stays, so its sha256 still blocks a second copy (S.6). Failed files stay. | Recovery from parser bugs. |
| [1.11] | The import writes events directly to the store. Verify is a separate step that reads from the store. | No redaction in the MVP, so no in-memory-only constraint. Each step can run again alone. |
| [1.12] | No redaction in the MVP: no IP hashing and no query-string stripping. | Internal system. Overrides the research map for the MVP. |
| [1.13] | Delivery = micro-batches pushed by the customer, not a per-line stream. Senders push gzip chunks every 30 s or 10 MB. | The CDN push sets the floor (30 s to 5 min). Pairing and the 30-min session gap wait anyway. A stream needs a broker, offsets and exactly-once logic. |
| [1.14] | The customer sends; we never fetch from their servers. CDN = vendor log push. Origin = Vector agent on each origin server, run by the customer; we supply `vector.toml`. Fluent Bit is also accepted. Vector sends raw lines; our importer is the only parser. | No SSH or credentials into customer hosts. Senders retry and buffer on disk. |
| [1.15] | One entry: `POST /ingest?site=<id>`, bearer token for each site. The body streams to the inbox; sha256 is calculated during the stream; insert `import_files` (status `new`); reply `202`. No parsing in the request. Body limit `INGEST_MAX_BYTES` (50 MB). No FastAPI `UploadFile`. | The only method Vector `http` and CDN HTTP push support. Flat memory. A slow parser cannot block senders. |
| [1.16] | Rate limit and byte quota for each site at `/ingest`. Over the limit: `429`. The sender keeps the data on its disk and retries. | One tenant cannot flood the system. No data lost. |
| [1.17] | No presigned URLs for machine senders. A CDN that writes only to its own bucket: the bucket reader lists it every `BUCKET_READER_INTERVAL_SECONDS` (read-only access) and copies new objects into the inbox. Dashboard upload: MVP = same streamed POST (limit `UPLOAD_MAX_BYTES`, 2 GB); later = presigned multipart. | Vector and CDN push cannot do the 2-step presigned flow. |
| [1.18] | `import_files.priority` is `live` (sender chunks, bucket copies) or `backfill` (dashboard upload, CLI). Backfill runs only when no live work waits. | A large upload of old logs must not delay the live data of other sites. |
| [1.19] | Inbox storage behind one interface (`Inbox`), S3 API. | Same code for S3, the customer's S3-compatible storage and SeaweedFS. |
| [1.20] | Test data = log files committed in `samples/logs/`, loaded through the normal upload or CLI path. The file name holds site, source and start time. See "Log file naming". | Test data goes through the same parser and pipeline as customer data. A dropped file gives only its name, so the name carries site and source. |
| [1.21] | `DELETE /api/imports/{id}`: one transaction under the site's fast-lane lock (transaction-level advisory lock). It deletes the file's events (also paired rows that hold its origin lines), resets paired partner files to `new` so their own lines are read again, deletes the file row, then deletes all views of the site and sets `in_views = false` on its events. The raw object is deleted after the commit. Refused (`409`) during a run, during an import, or when a partner's raw file is gone. | A paired row holds lines of two files. The incremental views only add, so a full rebuild of the site is the only correct result after rows are removed. The freed sha256 lets the same file load again. |
| [S.6] | Unique constraint on `import_files (site_id, sha256)`. | Two copies of one chunk (sender retry) can arrive at the same moment. The second insert fails and the reply is "already have it". |

Rules from the code (details of the decisions above):

| Rule | Why |
|---|---|
| `insert_new` uses `on conflict (site_id, sha256) do nothing`. A duplicate gets `200` with `duplicate: true` and the new object is deleted. | Idempotent sender retry (S.6). |
| The sha256 is unique for each site, not global. | Two sites can receive the same bytes. |
| An unknown site and a bad token give the same `401`. | The route does not leak site IDs. |
| `/ingest` compares the token hash with `hmac.compare_digest` (`token_matches`). The site YAML stores only `ingest_token_sha256`. | No plain token on disk. |
| `source` is optional when the site has one source. A site with two sources needs `source=cdn` or `source=origin` (`422` if missing or not in the site `sources`). | The user selects the source (1.5). |
| `POST /api/imports/upload` has no site token, no rate limit and no byte quota. It uses `API_TOKEN` (`/api/*` guard) and `UPLOAD_MAX_BYTES`. Priority `backfill`, entry `upload`. | Upload is a user action in the dashboard. |
| Only `/ingest` files (entry `ingest`) count toward the byte quota. Upload, CLI and bucket files do not. | Quota protects the machine entry. |
| The byte quota is read from Postgres (all API replicas share it). The request-rate window is in process memory: with N replicas the real limit is up to N times the setting. | Simple MVP limiter. |
| A body over the limit stops with `413` (declared `Content-Length` or counted while streaming). An empty body gives `400`. | Flat memory, early refusal. |
| The importer claims files with `FOR UPDATE SKIP LOCKED`: live before backfill, then oldest `received_at`. | Two workers never take one file (1.18). |
| `claim_next_file` sets `status = importing` and `attempts + 1` inside the caller's transaction. A crash leaves the file `new`. | Crash safety. |
| The import transaction covers all events and counts of one file slice. A failed file rolls back its partial events. | No half-imported file. |
| A parse or validation error rejects one line, never the step. A `psycopg.errors.DataError` fails that file only. Other database errors fail the step. | One bad file must not stop others. |
| A missing inbox object or any non-transient error: `mark_failed`, the step continues with the next file. | Failed files stay for repair. |
| A transient error (`BotoCoreError`, `OSError`, `ClientError` that is not "missing", `LockNotAvailable`) releases the file to `new` (`release_file`) and stops the step. After `MAX_RETRIES` (5) the file is `failed`. A lock wait does not count toward the limit. | The inbox or network is down, the file is fine. |
| When a file with `attempts > 1` restarts from line 0, its old events are deleted first (`delete_file_events`). | A retry must not leave half-imported rows. |
| A timestamp later than `now + FUTURE_LIMIT` (1 day) is rejected: `timestamp in the future`. | Bad clocks and attack data. |
| `events.pair_state` is `pending` when the site has both sources (`SiteConfig.pairs_sources`), else `single`. | The pairing step reads `pending` rows. |
| An origin line already merged in a paired row is a duplicate (match on `origin_line_key`, +-1 h). A CDN line already counted in a paired row is a duplicate (`line_key`, same `ts`). | A re-import after pairing must not double rows. |
| The overlap warning is the only guard when two files of one source cover the same time (`overlapping_files`: same site, same source, status `success`). | nginx has no request ID by default. |
| `force_reimport` of a CDN file also resets the origin files whose lines sit in its paired rows (all or none). | The origin row was deleted at pairing. |
| `reset_files` works only for files with status `success`, `failed` or `new` and a raw object that still exists. | A file with no raw object cannot be read again. |
| The bucket reader stores a mark `<bucket>/<key>#<size>#<etag>` in `bucket_objects` after each copy. It skips known marks, empty objects, and objects older than `RAW_RETENTION_DAYS`. One worker reads a target at a time (advisory lock). Each object commits alone. | A restart or a second worker must not copy an object twice. |
| The bucket reader streams the object through the API process (`copy_from`), so it works across endpoints and credentials and gives the sha256. | No cross-bucket copy dependency. |

## Log file naming

Rule (`log_names.parse_log_name`, `apps/dashboard/src/lib/log-name.ts`):

```
<site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log[.gz]
example__cdn__20261001T0000Z__gptbot-burst.log.gz
```

| Part | Value |
|---|---|
| `site` | A site ID from `apps/api/config/sites/`. Letters, digits, `-` and single `_`. |
| `source` | `cdn` or `origin`. It must be a source of that site. |
| `YYYYMMDDTHHMMZ` | UTC time of the first line. It sorts the files. The import uses the timestamp on each line. |
| `label` | Optional. What the file shows. |

- A dropped file gives the browser its name only, not its folder. So the name carries site and source.
- A name that does not follow the rule uses the site and source selected in the dashboard (upload) or `--site` and `--source` (CLI).
- `is_log_file` accepts `.log`, `.log.gz` and `.gz` for folder import. `parse_log_name` accepts only `.log` and `.log.gz`.
- `parse_log_name` does not check that `source` is `cdn` or `origin`. `import_local_file` checks it through `resolve_source`.

## Inbox object keys

| Entry | Key |
|---|---|
| `ingest`, `upload` | `<site>/<source>/<YYYY-MM-DD>/<uuid>.gz` or `.log` (by gzip magic bytes `1f 8b`) |
| `cli` | `cli/<site>/<uuid>-<file name>` |
| `bucket` | `bucket/<site>/<uuid>` |

## Adapters and CDN field maps

| Adapter | Input | Notes |
|---|---|---|
| `origin.py` | nginx "combined" log. Optional quoted request ID and `$request_time` after the user agent. | The request ID is read only when the site sets `request_id_header`. Result goes to `edge_request_id`. |
| `cdn.py` | `json` (one object per line), `csv` or `tsv` | Field names come from the field map. CSV and TSV take the column names from a header row, or from `columns:` in the map when `header: false`. |

- Field map file: `apps/api/config/cdn/<name>.yaml`. The site names it in `cdn_field_map`. `load_cdn_field_map` loads it. A missing map fails the file (`ValueError: site has no cdn_field_map` or `SiteNotFound`), not the step.
- Field map keys: `format`, `edge_request_id`, `timestamp`, `client_ip`, `method`, `path`, `status`, `bytes`, `user_agent`, `host`, `referrer`, `columns`, `header`, `edge_bot` (`column`, `bot_below`), `origin_header`.
- `edge_bot`: score below `bot_below` gives `edge_signal = bot`, else `human`. A missing or bad value gives `none`. No `edge_bot` block gives `none`.
- Timestamps in a CDN file: epoch seconds, epoch milliseconds (above `1e11`) or ISO 8601. No time zone means UTC.
- Rule: no CDN vendor name, header or field in code or the data model. Vendor differences live only in the field map.
- Validation (`common.validate`) rejects with these reasons: `invalid timestamp` (year outside 2000-2100), `invalid status` (not 100-599), `invalid method`, `missing path`, `path too long` (over 8 KiB), `invalid character` (NUL or bad UTF-8), `invalid size`, `invalid response time`, `invalid client ip`, `user agent too long` (over 2 KiB), `request id too long` (over 200). A referrer over 2 KiB is cut, not rejected.
- Other reject reasons: `line too long` (over `MAX_LINE_CHARS`, 64 K chars), `not a combined log line`, `invalid json`, `json line is not an object`, `invalid csv`, `no column names`, `wrong column count`, `timestamp in the future`.
- Blank lines are skipped and not counted.
- `ParsedLine` timestamps are stored in UTC. The row stores `status` for both sources; `edge_status` is set for CDN lines, `origin_status` for origin lines.

## Line key (dedupe)

`line_key()` = first 32 hex characters of sha256 over: `edge_request_id` (or `request_id`, or empty), UTC timestamp, method, path, status, client IP. Parts join with `\x1f`.

`events_dedupe` is a unique index on `(site_id, source, line_key, ts)`. `copy_events` loads rows into a temp table `events_stage`, then inserts with `on conflict ... do nothing`. Rejects, inserted rows and duplicates give `lines_total = lines_imported + lines_rejected + lines_duplicate`.

## Configuration

Settings are in `apps/api/src/config/settings.py` (env var = upper case name).

| Setting | Default | Effect |
|---|---|---|
| `s3_endpoint_url` | `None` (AWS S3) | S3-compatible endpoint of the inbox. |
| `s3_region` | `us-east-1` | Inbox region. |
| `s3_bucket` | `agent-analytics-inbox` | Inbox bucket. Created at first use if missing. |
| `s3_access_key_id`, `s3_secret_access_key` | `None` | Inbox credentials. |
| `ingest_max_bytes` | 50 MiB | Body limit of `POST /ingest` (`413`). |
| `upload_max_bytes` | 2 GiB | Body limit of `POST /api/imports/upload`. |
| `ingest_chunk_bytes` | 64 KiB | Read size of S3 reads and of the CLI file read. |
| `max_decompressed_bytes` | 20 GiB | A file larger than this after gunzip fails (`ObjectTooLarge`). |
| `ingest_rate_per_minute` | 120 | Requests for each site for each minute at `/ingest` (in memory). |
| `ingest_bytes_per_day` | 20 GiB | Byte quota for each site for each rolling day at `/ingest`. |
| `bucket_reader_enabled` | `False` | The worker runs the bucket reader only when `True`. |
| `bucket_reader_interval_seconds` | 60 | Time between bucket reads. |
| `bucket_reader_prefix` | `""` | Default prefix when a site `cdn_bucket` has none. |
| `tick_seconds` | 60 | Worker tick: how often the import runs. |
| `work_limit_bytes` | 200 MiB | Stop claiming files after this many bytes in one step (pipeline decision 7.9). |
| `work_limit_lines` | 2,000,000 | Stop claiming files after this many lines in one step. A file is cut into slices at this limit. |
| `raw_retention_days` | 7 | Cleanup deletes the object of a `success` file after this many days. Also the age limit of the bucket reader and of bucket marks. |
| `events_retention_days` | 30 | `events` partitions older than this are dropped (pipeline module). |
| `no_data_alert_minutes` | 60 | Default of the no-data alert. A site YAML key of the same name overrides it. |
| `api_token` | `None` | Guards `/api/*` (upload, list, delete). Not set = open. |

Site YAML keys used by ingestion (`config/sites/<site_id>.yaml`):

| Key | Effect |
|---|---|
| `sources` | `[cdn, origin]`, `[origin]` or `[cdn]`. Both = pairing on. |
| `cdn_field_map` | Name of `config/cdn/<name>.yaml`. Needed for a CDN source. |
| `request_id_header` | Name of the forwarded request-ID header in the nginx log. Enables `edge_request_id` for origin lines. |
| `ingest_token_sha256` | sha256 hex of the site token. No hash = every `/ingest` call is `401`. |
| `no_data_alert_minutes` | No-data alert limit for this site. |
| `cdn_bucket` | `{bucket, prefix, source}`. The bucket reader reads it. `source` default `cdn`. |

Constants in code: `BATCH_ROWS = 5000`, `FUTURE_LIMIT = 1 day`, `MAX_RETRIES = 5`, `SLICE_GROWTH_CAP = 10` (all in `importer/service.py`), `MAX_LINE_CHARS = 64 * 1024` (`store/inbox.py`), `MAX_REJECTS_PER_FILE = 10_000` (`store/import_files.py`), S3 multipart part size 8 MiB (`S3Inbox.part_bytes`).

## Interfaces

HTTP:

| Endpoint | Auth | Result |
|---|---|---|
| `POST /ingest?site=<id>[&source=cdn\|origin]` | `Authorization: Bearer <site token>` | `202 {file_id, duplicate:false}`, `200 {file_id, duplicate:true}`, `400` empty, `401`, `404` no, `413`, `422` source, `429` (`Retry-After: 60` rate, `3600` quota). Body: raw log, plain or gzip. |
| `POST /api/imports/upload?site=<id>[&source=...]` | `API_TOKEN` | `202` or `200` duplicate, same body as `/ingest`. Priority `backfill`. Unknown site gives `404`. |
| `GET /api/imports?site=&status=&limit=&offset=` | `API_TOKEN` | `ImportList` of `ImportFile` (counts, `min_ts`, `max_ts`, `error`, `delete_on`, `overlap_warning`). |
| `DELETE /api/imports/{file_id}` | `API_TOKEN` | `ImportDeleted {file_id, site_id, events_deleted, files_reimported}`. `404` unknown, `409` blocked. |

Python (`src.services.ingest`, `src.services.importer`):

| Function | Use |
|---|---|
| `accept_chunk(site_id, source, body, priority, entry, inbox, max_bytes) -> (file_id, duplicate)` | Stream a body to the inbox and insert `import_files`. Raises `PayloadTooLarge`, `EmptyBody`. |
| `object_key(site_id, source, gzipped, now=None) -> str` | Inbox key of a pushed chunk. |
| `check_site_token(site_id, token) -> bool` | Token check. |
| `check_rate_limit(site_id, size_hint=None, now=None) -> bool` | `True` = allowed. |
| `resolve_source(config, source) -> str` | Choose or check the source. `ValueError` text is the `422` reason. |
| `import_due_files(conn, site_id, inbox=None, now=None) -> dict` | Pipeline step `import`. Returns `files`, `files_failed`, `lines_total`, `lines_imported`, `lines_rejected`, `lines_duplicate`. |
| `import_local_file(path, site_id, *, now, force, source=None, inbox=None) -> dict` | CLI import. Returns `file_id`, `duplicate`, `reimport`, `counts` (with `--now`). |
| `delete_import(file_id, inbox=None) -> DeleteResult` | Delete (1.21). Raises `ImportNotFound`, `DeleteBlocked`. |
| `parse_log_name(name) -> LogName \| None`, `is_log_file(path) -> bool` | File name rule. |
| `line_key(line) -> str` | Dedupe key. |
| `BucketReader(inbox).read_new(conn, target, now=None) -> dict` | Returns `objects_new`, `objects_duplicate`, `objects_skipped`. |
| `targets_from_site_files() -> list[BucketTarget]` | Targets from site YAML `cdn_bucket`. |
| `cdn.make_parser(field_map)`, `origin.make_parser(request_id_header)` | Return `parse(text, line_no) -> ParsedLine \| Reject \| None`. |

Store (`src.store.import_files`, `events`, `inbox`, `quota`): `insert_new`, `get_file`, `get_by_sha`, `claim_next_file`, `mark_success`, `mark_failed`, `save_progress`, `release_file`, `reset_files`, `force_reimport`, `delete_file`, `add_rejects`, `list_rejects`, `list_files`, `count_files`, `files_waiting`, `live_work_waiting`, `sites_with_new_files`, `expired_success_files`, `mark_deleted`, `last_received_by_source`, `overlapping_files`, `origin_partners`, `cdn_partners`, `known_bucket_marks`, `remember_bucket_mark`, `prune_bucket_marks`; `events.copy_events`, `ensure_partitions`, `delete_file_events`, `delete_file_rows`, `drop_old_partitions`, `count_events`; `Inbox.put_stream`, `open_lines`, `delete`; `S3Inbox.list_objects`, `copy_from`, `ensure_bucket`; `quota.bytes_received_last_day`.

CLI (`apps/api/src/cli.py`): `uv run python -m src.cli import <file-or-folder> [--site ID] [--source cdn|origin] [--now] [--force]`. A folder imports every `.log`, `.log.gz` or `.gz` file in name order. `cleanup` runs the cleanup job.

Tables:

| Table | Content |
|---|---|
| `import_files` | One row for each file. `status` (`new`, `importing`, `success`, `failed`), `priority`, `entry` (`ingest`, `upload`, `cli`, `bucket`), `source`, `object_key`, `sha256`, `size_bytes`, counts, `min_ts`, `max_ts`, `error`, `attempts`, `retries`, `lines_done` (resume offset), `object_deleted_at`. Unique `(site_id, sha256)`. |
| `import_rejects` | `file_id`, `site_id`, `line_no`, `reason`. Cascade delete with the file. |
| `bucket_objects` | `(site_id, mark)` of copied bucket objects. |
| `events` | Output rows. Daily partitions. Written by `copy_events`. |

## Known limits

- Raw IPs and full URLs (with query strings) are stored. Redaction is necessary before customer use (1.12).
- nginx logs have no request ID by default. When two files overlap in time, the same lines can be counted twice. The system warns the user when the time ranges of two files of one source overlap (`overlap_warning` in the import list). It does not stop the import.
- Dashboard upload uses the same streamed POST (limit 2 GB). Presigned multipart upload is a later step.
- The `/ingest` rate window is per API process. With N replicas the real limit is up to N times `ingest_rate_per_minute`.
- A file is read from line 1 on each slice (a gzip stream has no random access). Slices grow with progress (`SLICE_GROWTH_CAP`), so a large file is read about 3 times at most.
- Memory bound: lines over 64 K chars are cut and rejected (`line too long`); gunzip output is capped at `max_decompressed_bytes`; the reject list keeps 10,000 entries for each file.
- A line key with no request ID uses time, method, path, status and client IP. Two different requests with the same values in the same second merge.
- Origin lines with `\"` in a quoted field are rejected (nginx writes a quote as `\x22`).
- The bucket reader runs only in the worker, only when `bucket_reader_enabled` is true, and only for CDN buckets set in site YAML.
- Force re-import has no API or dashboard control. It is a CLI option.
- The no-data alert has no baseline for a source that never sent a file.
- The sample logs are synthetic. Do not treat them as evidence of real agent behavior.

## Open questions

None recorded.

## How to change

| Change | Steps |
|---|---|
| Add a CDN vendor | Copy `config/cdn/example.yaml` to `config/cdn/<vendor>.yaml`. Set the columns. Set `cdn_field_map: <vendor>` in the site YAML. No code change. Test: add a case in `tests/importer/test_cdn_adapter.py`. |
| Add a log format | Add an adapter in `importer/adapters/`. Return `validate(...)` results. Add it to `_parser` in `importer/service.py`. Test beside `test_origin_adapter.py`. |
| Change a validation limit | Edit `adapters/common.py`. Update the reject reasons list above. Test in `test_origin_adapter.py` (`test_limits_at_boundary_ok`). |
| Change the dedupe key | Edit `dedupe.py`. Check the `events_dedupe` index, `copy_events` and pairing (`origin_line_key`). Update `tests/importer/test_dedupe.py`. |
| Change a limit, quota or default | Edit `config/settings.py` only. Update the Configuration table. |
| Add a site | Add `config/sites/<id>.yaml` with `sources` and `ingest_token_sha256` (`sha256` of the token). |
| Add an entry type | Extend the `entry` check in the migration, set the new value in `insert_new` callers. Decide if the byte quota counts it (`store/quota.py`). |
| Change the delete rules | Edit `importer/delete.py` and `store/import_files.py` (`reset_files`, partners). Test in `tests/importer/test_delete.py`. |
| Change the file name rule | Edit `log_names.py` and `apps/dashboard/src/lib/log-name.ts` together. Update `samples/logs/README.md`. |
| Change the sender config | See [deployment](../deployment/README.md). |

## Tests

Back end, from `apps/api` (Postgres on port 55432 needed, see `apps/api/README.md`):

```
uv run pytest tests/importer tests/ingest
```

| Folder or file | Covers |
|---|---|
| `tests/importer/test_origin_adapter.py`, `test_cdn_adapter.py` | Parsers, field maps, reject reasons. |
| `tests/importer/test_dedupe.py`, `test_events_store.py` | Line key, `copy_events`, partitions. |
| `tests/importer/test_importer.py`, `test_review_fixes.py`, `test_review_fixes2.py` | End to end import, work limits, slices, retries, priority, force re-import, bucket marks. |
| `tests/importer/test_local_file.py` | `import_local_file`, `--now`, duplicate, force. |
| `tests/importer/test_bucket_reader.py` | Bucket reader. |
| `tests/importer/test_delete.py` | Delete import, partner re-read. |
| `tests/importer/test_cleanup.py` | Raw file deletion and partition drop. |
| `tests/ingest/test_ingest_route.py`, `test_imports_route.py` | Routes: token, limits, `413`, `429`, duplicate, upload, list, overlap. |
| `tests/ingest/test_limits.py`, `test_quota.py` | Rate window and byte quota. |
| `tests/ingest/test_s3_inbox.py`, `test_inbox_limits.py`, `fake_s3.py` | S3 inbox, multipart, gunzip, line and size caps. |

## Related modules

- [pairing](../pairing/README.md): reads `pending` rows after the import; owns pair keys and windows.
- [pipeline](../pipeline/README.md): worker tick, lanes, locks, work limit (7.9), daily cleanup, retention and alerts.
- [store](../store/README.md): tables, migrations, partitions.
- [api](../api/README.md): routes, CLI, settings.
- [deployment](../deployment/README.md): Vector config, CDN push setup, Compose and Helm.
- [dashboard](../dashboard/README.md): Sources tab, upload, delete import.
- [testing](../testing/README.md): sample logs and the real-site test.
- [verification](../verification/README.md): reads imported events next.
