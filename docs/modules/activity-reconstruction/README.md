# Activity reconstruction

Activity reconstruction answers one question: "What did each client do, in what order, and where does the evidence stop?"
Input: classified events (`events` rows with a verdict). Output: sessions (visits) and hourly aggregates for the dashboard and the recommendation rules.
Pipeline step name: `views`. Entry point: `reconstruction.update_views`.

## Read this when

- You change how events are grouped into sessions (gap, client key, session cap).
- You change retry, loop, key-page, conversion or journey logic.
- You change a column of `sessions`, `open_sessions`, `session_events`, `page_stats`, `journey_steps` or `agents`.
- You change when a session is open or closed, or how late events are handled.
- You change session confidence or session gaps.
- You add a query that reads these tables (dashboard route or recommendation rule).
- You see wrong counts on the Sessions, Agents, Pages or Journeys screens.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/services/reconstruction/service.py` | `update_views`: builds parameters from settings and site config, runs the steps in one transaction. No SQL. |
| `apps/api/src/services/reconstruction/__init__.py` | Exports `update_views`. |
| `apps/api/src/services/reconstruction/README.md` | Short service note. |
| `apps/api/src/store/views.py` | All SQL of this module: staging, session build, id mapping, open/closed write, hourly refresh, `reset_site`, `mark_in_views`. Design notes are at the top of the file. |
| `apps/api/src/models/keys.py` | `client_key(user_agent, ip)` and `normalize_ip(ip)`. The importer calls them when it writes `events.client_key`. |
| `apps/api/src/services/registry/service.py` | `is_shared_ip(ip)`, `shared_ip_ranges()`. |
| `apps/api/config/registry/shared-ip.yaml` | Shared-IP ranges (extra to built-in CGN `100.64.0.0/10`). |
| `apps/api/src/services/site_config/service.py` | `load_site_config`: `key_pages`, `conversion_pages`, `journeys`, `sources`. |
| `apps/api/config/sites/example.yaml` | Example site config with `key_pages`, `conversion_pages`, `journeys`. |
| `apps/api/config/sites/piyushc.yaml` | Live-test site config (`key_pages`, `conversion_pages`; no `journeys`). |
| `apps/api/src/config/settings.py` | Session, retry and loop settings. |
| `apps/api/migrations/versions/0001_initial.py` | Creates `sessions`, `open_sessions`, `session_events`, `page_stats`, `journey_steps`, `agents`. |
| `apps/api/migrations/versions/0002_integration.py` | `events.in_views` and partial index `events_not_in_views`. |
| `apps/api/migrations/versions/0004_view_fixes.py` | `retry_paths` column and `*_last_seen` indexes on `sessions` and `open_sessions`. |
| `apps/api/src/store/queries.py` | Dashboard reads: `list_sessions`, `get_session`, `list_agents`, `get_agent`, `list_pages`, `get_page`, `list_journeys`. `SESSIONS_UNION` joins closed and open sessions. |
| `apps/api/src/store/recommendations.py` | Rule queries on the session and hourly tables. |
| `apps/api/src/store/retention.py` | `prune_older_than`: deletes old rows of these tables. |
| `apps/api/src/services/importer/delete.py` | Calls `views.reset_site` after an import file is deleted. |
| `apps/api/src/routes/sessions.py` | `/sessions`, `/sessions/{session_id}`. Builds the step list of one session. |
| `apps/api/src/routes/pages.py`, `journeys.py`, `agents.py`, `overview.py` | Endpoints that read the hourly tables. |
| `apps/api/tests/reconstruction/test_views.py` | Main tests of `update_views`. |
| `apps/api/tests/reconstruction/test_views_sessions.py` | Tests for unique ids, session cap, bounded hour refresh. |

## Data flow

```
 events (ready) + verdicts (append-only)            site config YAML
   in_views = false                                 key_pages · conversion_pages · journeys
   pair_state <> 'pending'                                   │
   verdict has traffic_class                                 │
        │                                                    │
        ▼                                                    ▼
 1 STAGE   _new (grouped) · _ungrouped (client_key NULL) · _dirty (clients + rebuild start)
        ▼
 2 SAME CLIENT?  events.client_key (UA + IP; IPv6 → /64)   no UA or IP ──► NOT GROUPED
        ▼
 3 SAME VISIT?   gap > 30 min (agent_client: 2 min) or age > 24 h = new session
        ▼
 4 SESSION FACTS + flags (retry, loop), confidence, gaps, journeys_reached
        ▼
 5 STABLE IDS    rebuilt session keeps the id of the oldest stored session it overlaps
        ▼
 6 WRITE         last_seen + (gap + margin) > now ?
                   ├─ yes ──► open_sessions   (delete + insert, version + 1)
                   └─ no  ──► sessions        (delete + insert, version + 1)
                 session_events (one row for each event of a rebuilt session)
        ▼
 7 CLOSE IDLE    open_sessions with no new event, past gap + margin ──► sessions
        ▼
 8 HOURS         delete + insert for the dirty hours ──► page_stats · agents · journey_steps
        ▼
 9 FLAG          events.in_views = true
        │
        ▼
 dashboard routes (store/queries.py) · recommendation rules (store/recommendations.py)
```

Sequence of one `update_views` call. Steps 1 to 9 run in one transaction (decision 4.7).

```
 pipeline          reconstruction.service        store/views.py              Postgres
    │ update_views(conn, site)  │                      │                        │
    │──────────────────────────►│ load_site_config     │                        │
    │                           │ begin transaction ───────────────────────────►│
    │                           │ stage_new_events ───►│ _new _dirty _ungrouped │
    │                           │                      │ _hours (temp tables)──►│
    │                           │ stage_sessions ─────►│ _ev0 _ev0r _starts     │
    │                           │                      │ _ev1 _ev _sess ───────►│
    │                           │ session_ips ────────►│                        │
    │                           │ registry.is_shared_ip (each IP)               │
    │                           │ finish_sessions ────►│ confidence · ids       │
    │                           │                      │ delete + insert ──────►│
    │                           │ close_idle_sessions ►│ open → sessions ──────►│
    │                           │ refresh_hours ──────►│ hourly delete + insert►│
    │                           │ mark_in_views ──────►│ in_views = true ──────►│
    │                           │ commit ──────────────────────────────────────►│
    │◄──────────────────────────│ counts dict          │                        │
```

Why a session row changes after it is first written. Logs arrive in 1-minute batches. A visit is longer than 1 minute. The same visit is seen in several runs.

```
 run 10:01   sees /pricing, /docs/api        ──► session #812: 2 pages, no failure          (open)
 run 10:02   sees /signup 403 ×3             ──► session #812: 3 pages, blocked, 3 retries  (open, same row)
 10:32+      no request for 30 min           ──► session #812 closed: final, never changes
```

The Sessions screen and rules P1 and P3 need the visit as one story, not as single lines.

How the writes behave:

| Table | Rows changed in each run | Write |
|---|---|---|
| `sessions` (closed visits, almost all rows) | 0 in the normal case | Append. Rebuilt only for late events (decision 4.6). |
| `open_sessions` (current visits) | A few thousand for a large site | Delete + insert for the rebuilt clients. Moved to `sessions` when the visit closes. |
| `page_stats`, `agents`, `journey_steps` | Dirty hours only (normally the current hour) | Delete + insert of the hourly rows. Never incremented. |

Each new event changes at most one open session. Cost grows with active visits, not with history. All rows have `site_id`.

Gap example (SQL window logic):

```
 client A:  10:00 10:01 10:03 ──(90 min)── 11:33 11:34
 new?        1     0     0                  1     0
 running SUM 1     1     1                  2     2   → session 1, session 2
```

## Rules and decisions

### Decisions

| ID | Decision | Why |
|---|---|---|
| [4.1] | Closed sessions are appended once. Only `open_sessions` and the hourly rows of the other views are rewritten, for the site with new events. Views are derived. History lives in `events` + `verdicts`. | A full rebuild reads all history every run and grows with every site and day. Open/closed keeps almost all writes as appends. |
| [4.2] | Retry = same client + same path again within 60 s after a 4xx/5xx. Loop = redirect back to a visited path, or same path 5 times or more. Values are in settings. | These are facts for the rules. Reconstruction reports, rules judge. |
| [4.3] | A shared-IP flag (CGN `100.64.0.0/10`, ranges in `config/registry/shared-ip.yaml`) lowers confidence. | Same IP is not the same agent (PDF §03.C). |
| [4.4] | Each session lists its gaps ("no CDN log: edge blocks unknown", "outcome unknown"). | PDF §03.C. |
| [4.5] | A session closes when its last event is older than the gap (30 min; agent clients 2 min) plus a delivery margin for late CDN files. | Late files can still add to a visit that looks finished. |
| [4.6] | A late event for an already closed range (backfill, very late file): re-compute the sessions of that client from the range start. Delete + insert in one transaction. Rare path. | Keeps closed rows correct without a full rebuild. |
| [4.7] | Upserts and deletes for one site run in one transaction. Readers see the old rows or the new rows, never a mix (Postgres MVCC). No table swap, no exclusive lock. | Safe for many sites in one table. Dashboard reads never wait. |

### Keys

| Key | Used in | What it joins |
|---|---|---|
| `edge_request_id` | pairing | CDN line + origin line = 1 event (1 request) |
| `client_key` | verification, activity reconstruction | All events of one (UA, IP) = "who" |
| verdict row | verification, classification | The label for "who" at a time |
| `session_id` | activity reconstruction | "who" + "one visit" = "who, when" |

Rule: group by `client_key` + time, not by verdict row. Why: a verdict covers many visits and can change during one visit.

### Labels

| Label | Meaning |
|---|---|
| Observed | counts, order, status codes, times |
| Inferred | grouping into a session, confidence |
| Unknown | outcome, intent, gaps |

### Session confidence

| Level | Condition |
|---|---|
| `high` | `verdict` = `VERIFIED` and IP not shared |
| `medium` | `verdict` = `CLAIMED`, or `traffic_class` 4 or 5, and IP not shared |
| `low` | Shared IP, or `registry_category` = `agent_client`, or `traffic_class` 6 (Unknown), or anything else |

The code checks `low` first (shared IP, agent client, class 6), then `high`, then `medium`. The session takes the verdict fields of its last event (highest `seq`).

### Implementation rules (from the code)

| Rule | Why |
|---|---|
| An event is new work when `in_views = false`, `pair_state <> 'pending'`, its verdict has a `traffic_class`, and `client_key` is set. Index `events_not_in_views` holds only these rows. | Cost follows the number of new events, not the history. A late event, a late CDN file or a late verdict is `in_views = false` and shows up by itself. |
| Events with `client_key` NULL (NOT GROUPED) get no verdict and no session. They count in the hourly views as `traffic_class` 6, `verdict` `UNKNOWN`, agent `unknown:ungrouped`. | The evidence has no identity, but the traffic must stay visible. |
| Only clients with new events are rebuilt. The rebuild starts at the earliest stored session of that client whose `last_seen` is within `max(session_gap_minutes, agent_session_gap_minutes)` of the first new event (or at the first new event). Sessions of that client with `started >=` that point are deleted and inserted again. | Normal case: the one open session. Late case ([4.6]): closed sessions too. |
| The gap of a client is the agent-client gap (2 min) when the last event of the client in the range has `registry_category` = `agent_client`. Otherwise it is the normal gap (30 min). The value applies to every gap of that client in the range. | Agent clients (for example a user-triggered fetcher) make short bursts. |
| A gap is "greater than": a difference of exactly 30 min stays in one session. | Matches `test_exactly_thirty_minutes_is_one_session`. |
| A session never lasts longer than `MAX_SESSION_HOURS` (24 h in `store/views.py`). The first event after that span starts a new session, even without a gap. | One endless client (monitor, crawler) causes a bounded rebuild. |
| Session starts come from a recursive walk from the first event. A rebuild from the start of a stored session gives the same cuts. | Stable cuts between runs. |
| `session_id` = `'s' ||` first 20 characters of `md5(site_id | client_key | started | first event id)`. | Deterministic id. |
| A rebuilt session keeps the id of the oldest stored session it overlaps (one old id goes to one rebuilt session at most). When sessions merge, the merged one keeps the earliest id. Any other rebuilt session gets its own hash id, re-hashed until it differs from every id in use (max 20 rounds, then `RuntimeError`). | A late earlier event moves `started` but not the id. Links and recommendation evidence stay valid. |
| `version` of a rebuilt session = highest stored version of its id + 1 (0 + 1 for a new id). | Readers can see that an open session changed. |
| Events inside a session are ordered by `(ts, id)`. `seq` starts at 1. `session_events` stores `(session_id, event_id, event_ts, seq)`. | Drill-down to evidence (PDF §03.D). |
| A session is open when `last_seen + (gap_min + delivery_margin_minutes) > now`, where `gap_min` is the largest gap of its events. `close_idle_sessions` moves open rows that pass the limit (using the `agent_client` category of the row's verdict) to `sessions` with `on conflict do nothing`. | Time rule only. A session with no new event still closes. |
| Retry (per event): the previous event of the same session and same path has status >= 400, and the time difference is `retry_window_seconds` or less. | [4.2] |
| Loop (per event): the path appears `loop_repeat_count` times or more in the session, or the previous event of the session has status 300 to 399 and the first event of this path is at least 2 events earlier. | [4.2] |
| `distinct_pages` = number of events that are the first of their path. `pages_in_order` = those paths in order, query string kept. | One entry for each page. |
| `key_pages_visited` = distinct pages whose path (or path without query string) is in `key_pages`. `reached_conversion` = any event with status < 400 whose path (or path without query string) is in `conversion_pages`. | Site config says which pages matter. Logs cannot. |
| `journeys_reached` = JSON object `{journey_id: highest step_no hit}`. A step matches an event when `step_path` equals the path or the path without query string. The steps need not be in order. | Funnel facts for the Journeys screen and rule P5. |
| `retry_paths` = distinct paths (with and without query string) where the session had a retry or loop. | P3 and the journey funnel count distinct sessions from this column, not hourly rows. |
| `gaps` = `["outcome unknown"]`, with `"no CDN log: edge blocks unknown"` first when `cdn` is not in the site `sources`, plus `"shared IP: may contain more than one agent"` when `shared_ip`. | [4.4] |
| Hourly rows are rebuilt from the events of the dirty hours: hours of new events, hours of ungrouped events, and hours of every event whose session id, retry flag or loop flag differs from the stored value. | Idempotent. Work does not follow the length of a session. |
| `page_stats.n_4xx` counts every 4xx (403 and 429 included). Error rate = `(n_4xx + n_5xx) / requests`. Block rate = `(n_403 + n_429) / requests`. | One definition for all readers. |
| Distinct counts over many hours (sessions, clients) come from the session tables, not from adding hourly values. | A session that spans hours counts once for each hour in the hourly rows. |
| `page_stats.tags` has `key` and/or `conversion` from site config. | Dashboard preset views. |
| `agents` has one row for each hour, `claimed_agent`, `traffic_class`. Clients with no bot name use `unknown:<ua_type>` or `unknown:class<N>`. `verification` and `confidence` come from the last event of the hour. `top_paths` = 5 most requested paths. | Agent directory (PDF "Agent directory"). |
| `journey_steps` rows list the steps up to the highest step a session reached in that hour, for each class. `sessions_retry_or_loop` counts sessions with a retry or loop event at that step. | Hourly step list. The exact funnel comes from `sessions.journeys_reached`. |
| `reset_site(conn, site_id)` deletes all view rows of the site and sets `in_views = false` on its events. | The incremental path only adds. It cannot see that rows are gone after an import file is deleted. |

## Configuration

Settings are environment variables (no prefix, upper case, for example `SESSION_GAP_MINUTES`). Defined in `apps/api/src/config/settings.py`.

| Setting | Default | Effect |
|---|---|---|
| `session_gap_minutes` | `30` | Idle time that starts a new session. Also the closing limit (with margin) for normal clients. |
| `agent_session_gap_minutes` | `2` | Same, for clients with `registry_category` = `agent_client`. |
| `delivery_margin_minutes` | `10` | Extra wait before a session closes, for late CDN files. |
| `retry_window_seconds` | `60` | Retry: max time between a failed request and the same path again. |
| `loop_repeat_count` | `5` | Loop: same path this many times in one session. |

Site config keys (YAML in `apps/api/config/sites/<site_id>.yaml`):

| Key | Default | Effect |
|---|---|---|
| `key_pages` | `[]` | Paths tagged `key`. Counted in `key_pages_visited`. |
| `conversion_pages` | `[]` | Paths tagged `conversion`. Set `reached_conversion`. |
| `journeys` | `[]` | List of `{id, steps: [paths], critical}`. `critical` is not used by reconstruction. |
| `sources` | `[]` | If `cdn` is missing, sessions get the gap "no CDN log: edge blocks unknown". |

Other config:

| Name | Default | Effect |
|---|---|---|
| `MAX_SESSION_HOURS` (constant in `store/views.py`) | `24` | Maximum length of one session. |
| `config/registry/shared-ip.yaml` `ranges[].cidr` | Cloudflare WARP/Workers ranges | Extra shared-IP ranges. CGN `100.64.0.0/10` is always shared. |

## Interfaces

Service:

| Function | Notes |
|---|---|
| `reconstruction.update_views(conn: AsyncConnection, site_id: str, now: datetime \| None = None) -> dict` | Pipeline step `views` in `FAST_STEPS`. Returns counts: `clients_recomputed`, `sessions_written`, `sessions_open`, `sessions_closed`, `sessions_recomputed_closed`, `hours_updated`, `events_flagged`. |

Store (`src/store/views.py`):

| Function | Notes |
|---|---|
| `stage_new_events(conn, site_id, now, gap_max_minutes) -> dict` | Fills temp tables `_new`, `_dirty`, `_ungrouped`, `_hours`. Returns `{"clients": n}`. |
| `stage_sessions(conn, site_id, p) -> int` | Builds `_ev` and `_sess`. Returns the number of sessions built. |
| `session_ips(conn) -> list[str]` | Distinct client IPs of `_sess`. |
| `finish_sessions(conn, site_id, p, shared_ips, base_gaps) -> dict` | Sets confidence and gaps, maps ids, writes `sessions`, `open_sessions`, `session_events`. Returns `open`, `closed`, `recomputed_closed`. |
| `close_idle_sessions(conn, site_id, now, gap, agent_gap, margin) -> int` | Moves idle open sessions to `sessions`. |
| `refresh_hours(conn, site_id, p) -> int` | Rebuilds hourly rows. Returns the number of hours. |
| `mark_in_views(conn, site_id) -> int` | Sets `events.in_views = true` for the staged events. |
| `reset_site(conn, site_id) -> int` | Full reset of the site views. Used by `importer/delete.py`. |

Tables read by other modules:

| Table | One row is | Key columns |
|---|---|---|
| `sessions` | One closed visit | PK `(site_id, session_id)`. `version`, `client_key`, `verdict_id`, `claimed_agent`, `user_agent`, `client_ip`, `edge_signal`, `traffic_class`, `confidence`, `started`, `last_seen`, `requests`, `distinct_pages`, `pages_in_order[]`, `key_pages_visited`, `reached_conversion`, `has_retry`, `has_loop`, `retries`, `shared_ip`, `gaps[]`, `status_counts` (jsonb), `journeys_reached` (jsonb), `retry_paths[]` |
| `open_sessions` | One visit still active | Same columns (`like sessions including all`). Moves to `sessions` when it closes. |
| `session_events` | One event inside one visit | PK `(site_id, session_id, seq)`. `event_id`, `event_ts`. |
| `page_stats` | One hour x path x class | PK `(site_id, hour, path, traffic_class)`. `tags[]`, `requests`, `sessions`, `clients`, `median_bytes`, `n_2xx`, `n_3xx`, `n_403`, `n_429`, `n_4xx`, `n_5xx`, `retries` |
| `journey_steps` | One hour x journey x class x step | PK `(site_id, hour, journey_id, traffic_class, step_no)`. `step_path`, `sessions_reached`, `sessions_retry_or_loop` |
| `agents` | One hour x claimed identity x class | PK `(site_id, hour, claimed_agent, traffic_class)`. `verification`, `confidence`, `first_seen`, `last_seen`, `requests`, `sessions`, `distinct_pages`, `top_paths[]` |

Readers:

- Dashboard: `store/queries.py` (`list_sessions`, `get_session`, `list_agents`, `get_agent`, `list_pages`, `get_page`, `list_journeys`). Always read sessions through `SESSIONS_UNION` so that open sessions show with `in_progress`.
- Recommendation rules: `store/recommendations.py` (`p1_product_discovery` to `p5_full_journey`, `journey_funnel`, `agents_for_sessions`, `time_pattern`, `count_events`, `sample_events`, `event_ids`).

## Known limits

- Frequent writes on `open_sessions` and the hourly tables leave dead row versions. Tune autovacuum for these tables.
- Reconstruction reports facts. It does not know the task outcome: the outcome is always Unknown.
- Grouping into sessions is inferred (same `client_key`, no gap). Two agents behind one `(UA, IP)` look like one client. The shared-IP flag lowers confidence but does not split the client.
- Journey steps need not be reached in order. `journeys_reached` stores only the highest step hit.
- Retry, loop and the gap limit are global settings, not set for each site.
- `open_sessions` is not pruned by `store/retention.py`. Idle rows move to `sessions` first, and `sessions` is pruned by `last_seen`.
- Key pages that no client requested have no row in `page_stats`. The Pages route adds them with 0 requests (`routes/pages.py`).

## Open questions

None recorded.

## How to change

| Task | Steps |
|---|---|
| Change a gap, margin, retry or loop value | Edit the default in `src/config/settings.py`. Update the Configuration table here. Run `tests/reconstruction`. |
| Add a key page, conversion page or journey | Edit `config/sites/<site_id>.yaml`. No code change. New journey steps show for new events. Old sessions keep their stored `journeys_reached` until they are rebuilt. |
| Add a shared-IP range | Add `{ name, cidr }` to `config/registry/shared-ip.yaml`. Applies to sessions built after the change. |
| Add a column to a session or hourly table | Add an Alembic migration (apply it to `sessions` and `open_sessions` together). Add the column to `_sess`, to the `columns` and `select` lists in `finish_sessions`, and to `SESSION_COLUMNS` in `store/queries.py` if the API shows it. Add a test in `tests/reconstruction/test_views.py`. Update the Interfaces table. |
| Change retry or loop logic | Edit `FLAGGED` in `store/views.py`. Also edit `build_steps` in `routes/sessions.py`, which recomputes flags for the step list. Run `tests/reconstruction` and `tests/api/test_sessions.py`. |
| Change confidence rules | Edit the `update _sess set confidence` statement in `finish_sessions`. Also edit `confidence_reason` in `routes/sessions.py`. Update `test_confidence_rules`. |
| Change the client key | Edit `src/models/keys.py`. All existing `client_key` values change: also read the verification module. |
| Force a full rebuild of one site | Call `views.reset_site(conn, site_id)`. The next `update_views` rebuilds from the remaining events. |
| Add a new hourly aggregate | Add the table in a migration. Delete + insert it by hour inside `refresh_hours`. Add the table to `_PRUNE` in `store/retention.py` and to `reset_site`. |

## Tests

| Path | Covers |
|---|---|
| `apps/api/tests/reconstruction/test_views.py` | Gap split (30 min, 2 min for agent clients), retry, loop, key and conversion pages, journeys, latest verdict, NOT GROUPED, confidence, gaps, open/closed, version, idempotence, late events, stable ids, merge, hourly views, transaction rollback, `in_views` flag. |
| `apps/api/tests/reconstruction/test_views_sessions.py` | Unique ids after a split, 24 h session cap, bounded hour refresh. |
| `apps/api/tests/api/test_sessions.py`, `test_pages_journeys_runs.py`, `test_agents.py` | API reads of these tables. |
| `apps/api/tests/e2e/test_pipeline_e2e.py`, `test_delete_e2e.py` | Full path through `views`; `reset_site` after a delete. |

Run from `apps/api` (needs Postgres on port 55432, see `apps/api/README.md`):

```
uv run pytest tests/reconstruction
```

## Related modules

- [pairing](../pairing/README.md): produces the events and `pair_state`.
- [verification](../verification/README.md): `client_key` verdicts, `VERIFIED` and `CLAIMED`.
- [classification](../classification/README.md): `traffic_class` and `registry_category`.
- [recommendations](../recommendations/README.md): rules P1 to P5 read the tables of this module.
- [pipeline](../pipeline/README.md): runs `views` as the last fast-lane step.
- [store](../store/README.md): Postgres access and retention.
- [api](../api/README.md): routes that read these tables.
- [dashboard](../dashboard/README.md): Sessions, Agents, Pages and Journeys screens.
- [ingestion](../ingestion/README.md): importer writes `events.client_key`.
