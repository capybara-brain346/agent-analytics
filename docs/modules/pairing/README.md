# Pairing

Pairing joins the CDN log line and the origin log line of one request into one event.
Input: `events` rows with `pair_state = 'pending'` (written by import). Output: `paired` rows and `single` rows. One request is one event.

The code is provider-neutral. No CDN vendor name, header or field is in the code or the data model. Vendor differences live only in YAML field maps.

## Read this when

- You change how CDN and origin lines match (pair key, time window, tie-break).
- You change when an unpaired row becomes `single` or gets `cdn_bypass`.
- You add support for a new CDN (field map in `apps/api/config/cdn/`).
- You change the `edge_request_id` column or the origin log format (`request_id_header`).
- You write or check the customer setup for nginx (`real_ip`, request-ID header in `log_format`).
- You explain why the nginx `$request_id` cannot be the pair key.
- You debug a site where events stay `pending`, or where the paired share is low.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/services/pairing/service.py` | `pair_events`: the pipeline step. Pairs pending rows, then expires old ones. |
| `apps/api/src/services/pairing/__init__.py` | Exports `pair_events`. |
| `apps/api/src/services/pairing/README.md` | Short pointer to this module. |
| `apps/api/src/store/pairing.py` | All SQL: `PAIR_ROUND`, `EXPIRE`, `pair_pending`, `expire_pending`. |
| `apps/api/config/cdn/example.yaml` | Template CDN field map (demo data). Copy it for a new CDN. |
| `apps/api/config/cdn/cloudflare.yaml` | Field map for the Cloudflare Pages test capture (one source, no pairing). |
| `apps/api/config/sites/example.yaml` | Site config that pairs: `sources: [cdn, origin]`, `cdn_field_map`, `request_id_header`. |
| `apps/api/config/sites/piyushc.yaml` | Site config with one source (`sources: [cdn]`): no pairing. |
| `apps/api/src/services/site_config/service.py` | `SiteConfig.pairs_sources`, `load_cdn_field_map`. |
| `apps/api/src/services/importer/adapters/cdn.py` | CDN adapter. Reads a field map and fills `edge_request_id`. |
| `apps/api/src/services/importer/adapters/origin.py` | nginx adapter. Reads the quoted request-ID field into `edge_request_id`. |
| `apps/api/src/services/importer/service.py` | Sets `pair_state` to `pending` when the site pairs, else `single`. Sets `edge_status` or `origin_status` by source. |
| `apps/api/src/store/events.py` | `copy_events` skips lines already merged in a paired row. `delete_file_rows` removes paired rows that hold lines of a file. |
| `apps/api/src/store/import_files.py` | Finds the paired partner files of a file (`origin_file_id`). |
| `apps/api/src/services/pipeline/service.py` | Runs the step `("pair", pairing.pair_events)` after `import` in `FAST_STEPS`. |
| `apps/api/src/config/settings.py` | `pair_window_seconds`, `pair_wait_minutes`, `pair_hard_limit_hours`. |
| `apps/api/migrations/versions/0001_initial.py` | `events` columns `source`, `edge_status`, `origin_status`, `edge_request_id`, `pair_state`, `cdn_bypass`; index `events_pending`. |
| `apps/api/migrations/versions/0002_integration.py` | Columns `origin_line_key`, `origin_file_id`; index `events_origin_line_key`. |
| `apps/api/tests/pairing/test_pair_events.py` | Pairing tests. |

## Data flow

```
 CDN log file ──► import ──► CDN adapter ──reads──► config/cdn/<name>.yaml
 (vendor format)             │                       (column names)
                             ▼
                    events row: source='cdn', pair_state='pending'
                    edge_request_id, edge_status = status
                                                            │
 origin log file ─► import ──► origin adapter               │
 (nginx combined     │         (quoted request-ID field)    ▼
  + request ID)      ▼                              ┌───────────────┐
                    events row: source='origin',    │  pair_events  │
                    pair_state='pending',           │  (pair step)  │
                    edge_request_id, origin_status  └───────┬───────┘
                             │                              │
                             └──────────────►───────────────┤
                                                            ▼
              ┌─────────────────────────────┬───────────────────────────────┐
              ▼                             ▼                               ▼
   PAIR_ROUND: match on            EXPIRE: wait time over,          no match yet:
   site + edge_request_id          no queued file of the            row stays pending
   + method + path                 other source                     (next tick)
   + time within ±window                    │
              │                             ▼
              ▼                    pair_state='single'
   CDN row updated:                (origin row also: cdn_bypass=true)
   source='paired', merged fields
   origin row deleted
```

Where the request ID comes from (why only the CDN ID pairs):

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

Client IP at the origin:

```
 Agent 20.171.1.5 ──► CDN ──(X-Forwarded-For: 20.171.1.5)──► nginx
                                                              │ real_ip module,
                                                              │ trust CDN ranges only
                                                              ▼
                                         origin log: client IP = 20.171.1.5
```

Pair key:

```
 CDN line ──► edge_request_id ◄── origin line
 (field map)   generic field      (header name = site setting
               in our schema       `request_id_header`)
                    │
                    ▼
   key: edge_request_id + method + path, time within ±N s
                    │
                    ▼
         one event: edge fields + origin fields
```

Pair step sequence (one fast-lane run):

```
 pipeline        pair_events           store.pairing              Postgres
    │ pair step      │                       │                       │
    │───────────────►│ pairs_sources?        │                       │
    │                │ (no: return zeros)    │                       │
    │                │ pair_pending(window)  │                       │
    │                │──────────────────────►│ PAIR_ROUND            │
    │                │                       │──────────────────────►│
    │                │                       │◄── paired, deleted ───│
    │                │                       │ repeat until paired=0 │
    │                │◄── total paired ──────│                       │
    │                │ expire_pending(       │                       │
    │                │  cutoff, hard_cutoff) │                       │
    │                │──────────────────────►│ EXPIRE                │
    │                │                       │──────────────────────►│
    │                │◄── single, bypass ────│◄──────────────────────│
    │◄── counts ─────│                       │                       │
```

## Rules and decisions

### Cases

| Case | CDN log | Origin log | Result |
|---|---|---|---|
| Blocked at edge | yes | no | CDN-only event (block) |
| Served from CDN cache | yes | no | CDN-only event (cache hit) |
| Forwarded to origin | yes | yes | PAIRED event (edge status + origin status) |
| Origin hit directly | no | yes | ORIGIN-ONLY event (CDN bypass: `cdn_bypass = true`) |

### Decisions

1. **[1b.1]** Pair CDN and origin logs by default. One request = one event.
   Why: edge blocks and origin failures for the same request are both visible.
2. **[1b.2]** nginx logs the real client IP from `X-Forwarded-For` (`real_ip` module).
   Why: this is standard and works with any CDN. Without it, the origin log shows the CDN IP and Verify fails.
3. **[1b.3]** `real_ip` trusts `X-Forwarded-For` only from the CDN IP ranges (`set_real_ip_from`).
   Why: any client can send a false `X-Forwarded-For`. A spoofer could copy a bot IP and get VERIFIED.
4. **[1b.4]** The schema has one generic field, `edge_request_id`. The CDN adapter reads it through a field map (YAML). The name of the request-ID header is a site setting (`request_id_header`).
   Why: no vendor in the code or data model. A new CDN is a new config file, not new code.
5. **[1b.5]** Pair key = `edge_request_id` + `method` + `path` + time window.
   Why: a vendor request ID is not trusted as unique.
6. **[1b.6]** The pair step runs after the import step. Unpaired events wait for a time window, then stay single.
   Why: CDN and origin files arrive at different times and in any order.
7. **[1b.7]** A site with no request ID in both logs does not pair. Use one source only (rule of the outermost hop).
   Why: without a shared ID, two logs of one request give a double count.

### Behavior in the code

These rules come from `apps/api/src/store/pairing.py` and `apps/api/src/services/pairing/service.py`.

- A site pairs only when `sources` contains both `cdn` and `origin` (`SiteConfig.pairs_sources`). Else `pair_events` returns zero counts and changes nothing.
- The import step sets `pair_state = 'pending'` for all rows of a pairing site, and `single` for other sites.
- `PAIR_ROUND` matches a CDN row to an origin row when both are `pending`, in the same site, with the same `edge_request_id` (not null), the same `method` (null-safe), the same `path`, and `o.ts` within `±pair_window_seconds` of `c.ts`.
  Why: see [1b.5].
- Each CDN row picks its nearest origin row, and each origin row picks its nearest CDN row. Only mutual picks pair. Ties break on `id`. Left-over rows compete again in the next round. `pair_pending` repeats rounds until a round pairs nothing.
  Why: the result is one-to-one and nearest-first, even when a request ID repeats.
- A pair keeps the CDN row (its `id`, `ts`, `client_ip`, `user_agent`). The origin row is deleted.
  Why: the paired row keeps one identity for the later steps.
- Field merge on a pair:

  | Column | Value |
  |---|---|
  | `source`, `pair_state` | `paired`, `paired` |
  | `origin_status` | `coalesce(o.origin_status, o.status)` |
  | `status` | `coalesce(c.edge_status, c.status, o.origin_status, o.status)`: the edge status is final (an edge block of 403 stays 403 when the origin said 200) |
  | `request_id` | `coalesce(o.request_id, c.request_id)` |
  | `response_time_ms` | `coalesce(o.response_time_ms, c.response_time_ms)` |
  | `bytes_sent`, `host`, `referrer` | `coalesce(c.<col>, o.<col>)` |
  | `origin_line_key`, `origin_file_id` | `line_key` and `file_id` of the deleted origin row |

- The paired row keeps `origin_line_key` and `origin_file_id`.
  Why: a re-import of the origin file does not insert the merged line again (`copy_events` skips it), and a delete of a file also removes the paired rows that hold its lines (`delete_file_rows`).
- The `EXPIRE` query makes a `pending` row `single` when `imported_at < now - pair_wait_minutes`.
  A row without `edge_request_id` is not made single at once. It waits like the others (one rule for all rows), and is single after the wait.
  An origin row that becomes single also gets `cdn_bypass = true`.
- A row older than the wait still keeps waiting while an `import_files` row of the other source has status `new` or `importing`. The row expires in any case when `imported_at < now - pair_hard_limit_hours`.
  Why: lines of a large backfill may pair with this row, but reach it only after many ticks.
- A second run with the same `now` changes nothing (idempotent).

## Configuration

| Setting | Default | Effect |
|---|---|---|
| `pair_window_seconds` (`apps/api/src/config/settings.py`) | `5` | Time window: origin `ts` within ± this many seconds of the CDN `ts`. |
| `pair_wait_minutes` (`settings.py`) | `10` | An unpaired row waits this long after import, then becomes `single`. |
| `pair_hard_limit_hours` (`settings.py`) | `24` | Upper limit for the wait while the other source still has queued files. |
| `sources` (site YAML, `apps/api/config/sites/<site>.yaml`) | none | Both `cdn` and `origin` turn pairing on. One source turns it off. |
| `cdn_field_map` (site YAML) | none | Name of the file in `apps/api/config/cdn/` (without `.yaml`) for the CDN lines of the site. |
| `request_id_header` (site YAML) | none | Name of the request-ID header that the customer logs in nginx. Without it, the origin adapter sets `edge_request_id` to null and the origin rows cannot pair. |

`settings.py` reads each setting from the environment variable with the same name in upper case (for example `PAIR_WINDOW_SECONDS`).

### CDN field map keys (`apps/api/config/cdn/<name>.yaml`)

Keys that the CDN adapter (`importer/adapters/cdn.py`) reads:

| Key | Default | Effect |
|---|---|---|
| `format` | `json` | `json`, `csv` or `tsv`. Other values raise an error. |
| `columns` | none | Column names for a CSV or TSV file without a header. |
| `header` | `true` | CSV or TSV: the first line holds column names. |
| `edge_request_id` | none | Vendor column with the request ID. |
| `timestamp`, `client_ip`, `method`, `path`, `status`, `bytes`, `user_agent` | none | Vendor column for each generic field. |
| `host`, `referrer` | none | Optional vendor columns. |
| `edge_bot.column`, `edge_bot.bot_below` | none | Optional bot signal: score below `bot_below` = `bot`, else `human`, missing = `none`. Remove the block when the CDN has no bot signal. |
| `origin_header` | none | Header the CDN sends to origin. This key only documents the setup. The adapter does not read it. |

## Interfaces

| Name | Where | Contract |
|---|---|---|
| `pair_events(conn: AsyncConnection, site_id: str, now: datetime \| None = None) -> dict` | `apps/api/src/services/pairing/service.py` | Returns `{"paired": int, "single": int, "cdn_bypass": int}`. The pipeline calls it as step `pair` and injects `now` (`_STEP_ARGS`). |
| `pair_pending(conn, site_id, window_seconds) -> int` | `apps/api/src/store/pairing.py` | Runs `PAIR_ROUND` until no pair is found. Returns the pair count. |
| `expire_pending(conn, site_id, cutoff, hard_cutoff) -> tuple[int, int]` | `apps/api/src/store/pairing.py` | Returns `(single, bypass)`. |
| `SiteConfig.pairs_sources` | `apps/api/src/services/site_config/service.py` | `True` when `sources` has `cdn` and `origin`. |
| `load_cdn_field_map(name: str) -> dict` | `apps/api/src/services/site_config/service.py` | Reads `config/cdn/<name>.yaml`. Raises `SiteNotFound` for a bad or missing name. |

Columns of table `events` that other modules read:

| Column | Meaning |
|---|---|
| `source` | `cdn`, `origin` or `paired`. |
| `pair_state` | `pending`, `paired` or `single`. Later steps skip `pending` rows (partial indexes `events_no_verdict` and `events_not_in_views`). |
| `edge_status`, `origin_status`, `status` | Edge status, origin status, final status. See the merge table. |
| `edge_request_id` | The shared pair ID. |
| `cdn_bypass` | `true` for an origin-only row that expired. |
| `origin_line_key`, `origin_file_id` | Identity of the merged origin line. |

The overview route (`apps/api/src/routes/overview.py`) computes the paired share as `paired / (paired + origin)` for a pairing site. The events route (`apps/api/src/routes/events.py`) returns `source`, `pair_state`, `edge_status`, `origin_status`, `edge_request_id` and `cdn_bypass`.

## Known limits

- With one source, there is no pairing and no `cdn_bypass` flag. CDN-only and origin-only sites cannot see edge blocks and origin failures together.
- Pairing needs a shared request ID in both logs ([1b.7]). Rows without `edge_request_id` end as `single`. An origin row without it is also flagged `cdn_bypass`, although it may not be a bypass.
- The pair row keeps the client IP and user agent of the CDN row. The origin IP is not used after pairing.
- `status` of a paired row is the edge status. The origin status is only in `origin_status`.
- The origin adapter reads the quoted request-ID field by position. It does not check the header name (`request_id_header` is only an on/off switch for that field).
- The MVP has one tested field map layout (the demo data). Other CDN vendors need a YAML file and a check of their log format (`format`, timestamp format, column names).

## Open questions

- The value of the time window (`pair_window_seconds`, now `5`) must be checked on real data. The demo data is synthetic.

## How to change

Add a CDN:

1. Copy `apps/api/config/cdn/example.yaml` to `apps/api/config/cdn/<vendor>.yaml`.
2. Set `format` and each column name to the vendor log column. Set `edge_request_id` to the column with the request ID. Remove the `edge_bot` block if the CDN has no bot signal.
3. Set `cdn_field_map: <vendor>` in `apps/api/config/sites/<site>.yaml`. Add `sources: [cdn, origin]` and `request_id_header` (the header the CDN sends to origin) to pair.
4. Do not add a vendor name in code. If the vendor needs a new format or field, change the generic adapter, not a vendor branch.
5. Test: add a case to `apps/api/tests/importer/test_cdn_adapter.py` (adapter) and run `uv run pytest tests/pairing tests/importer`.

Change the pair window or wait: change the default in `apps/api/src/config/settings.py`, or set the environment variable. Update the table in this file.

Change the match rule or the merge: edit `PAIR_ROUND` in `apps/api/src/store/pairing.py`. Keep the one-to-one rule. Add or change a case in `apps/api/tests/pairing/test_pair_events.py`.

Change the expiry rule: edit `EXPIRE` in `apps/api/src/store/pairing.py` and the comment in `apps/api/src/services/pairing/service.py`.

Make a site pair: set `sources: [cdn, origin]` in the site YAML, make both logs carry the same request ID, and set `request_id_header`.

Required origin config (customer side, for the setup guide):

- nginx `real_ip`: `set_real_ip_from <CDN ranges>;` and `real_ip_header X-Forwarded-For;`. List only CDN ranges in `set_real_ip_from`.
- nginx `log_format`: the `combined` format, then the forwarded request-ID header as a quoted field (for example `"$http_x_request_id"`). An optional `$request_time` field may follow. The header name must match `request_id_header`.

## Tests

- `apps/api/tests/pairing/test_pair_events.py`: exact match and merge, edge status is final, window edges, nearest-first one-to-one, extra candidate stays pending, method or path mismatch, wait expiry and `cdn_bypass`, missing request ID, late arrival in both orders, non-pairing site no-op, other site untouched, idempotent rerun.
- Related: `apps/api/tests/importer/test_cdn_adapter.py`, `apps/api/tests/importer/test_origin_adapter.py`, `apps/api/tests/importer/test_delete.py` (paired rows and delete), `apps/api/tests/e2e/test_pipeline_e2e.py` (full path with pairing).
- Command, from `apps/api`: `uv run pytest tests/pairing`. Tests need Postgres on port 55432 (see `apps/api/README.md`).

## Related modules

- [ingestion](../ingestion/README.md): adapters, import, `pair_state = 'pending'`, dedupe.
- [verification](../verification/README.md): uses the client IP that real_ip restores.
- [pipeline](../pipeline/README.md): runs the `pair` step in the fast lane.
- [store](../store/README.md): `events` table and partitions.
- [deployment](../deployment/README.md): customer setup and CDN capture.
- [architecture](../architecture/README.md): provider-neutral rule.
