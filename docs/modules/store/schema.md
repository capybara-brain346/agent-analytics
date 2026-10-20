# Store schema

One PostgreSQL database holds all tables. The source of truth is `apps/api/migrations/versions/`. This file lists every table: purpose, key columns, keys and indexes, writers and readers. See [README.md](README.md) for the rules.

Writers and readers are modules. Only `src/store/` runs the SQL (rule S.3).

## Table list

| Table | Group | Created in |
|---|---|---|
| `import_files` | Import | `0001` |
| `import_rejects` | Import | `0001` |
| `bucket_objects` | Import | `0003` |
| `events` | Events (partitioned) | `0001` |
| `verdicts` | Verify and classify | `0001` |
| `ip_list_snapshots` | Verify | `0001` |
| `sessions` | Activity reconstruction | `0001` |
| `open_sessions` | Activity reconstruction | `0001` |
| `session_events` | Activity reconstruction | `0001` |
| `page_stats` | Activity reconstruction | `0001` |
| `journey_steps` | Activity reconstruction | `0001` |
| `agents` | Activity reconstruction | `0001` |
| `recommendation_runs` | Recommendations | `0001` |
| `recommendations` | Recommendations | `0001` |
| `llm_text_cache` | Recommendations | `0001` |
| `pipeline_runs` | Pipeline | `0001` |
| `site_work` | Pipeline | `0001` |
| `alerts` | Pipeline | `0001` |

Every table has a `site_id text` column, except `ip_list_snapshots`. `ip_list_snapshots` is shared by all sites.

## Import

### `import_files`

- Purpose: one row for each raw file (or chunk) in the S3 inbox. It is the import queue and the file state machine.
- Key columns:
  - `id uuid` (PK), `site_id`, `sha256`, `object_key`, `size_bytes`.
  - `source` in `origin`, `cdn`.
  - `entry` in `ingest`, `upload`, `cli`, `bucket`.
  - `priority` in `live`, `backfill`.
  - `status` in `new`, `importing`, `success`, `failed`.
  - Counters: `lines_total`, `lines_imported`, `lines_rejected`, `lines_duplicate`.
  - `min_ts`, `max_ts`: event time range of the file.
  - `attempts`, `retries`, `lines_done` (resume offset of a sliced import), `object_deleted_at`.
- Keys and indexes:
  - `unique (site_id, sha256)`: rule S.6.
  - `import_files_queue (site_id, status, priority, received_at)`.
  - `import_files_received (site_id, received_at desc)`.
- Writers: ingestion (`insert_new`, `delete_file`), importer (`claim_next_file`, `mark_success`, `mark_failed`, `save_progress`, `release_file`), cleanup (`mark_deleted`), import routes (`force_reimport`, `reset_files`).
- Readers: importer, pairing (`expire_pending` checks queued files), alerts service (`last_received_by_source`), the `/ingest` quota (`quota.bytes_received_last_day`), API (`list_files`, `count_files`).
- The row stays after the raw object is deleted. Its `sha256` keeps blocking a second copy.

### `import_rejects`

- Purpose: lines that the importer rejected. Line number and short reason only. No line text.
- Key columns: `id` (PK), `file_id` (FK to `import_files`, `on delete cascade`), `site_id`, `line_no`, `reason`.
- Indexes: `import_rejects_file (file_id, line_no)`.
- Writers: importer (`add_rejects`). Cap: `MAX_REJECTS_PER_FILE` = 10000 rows for each file. Reason cut to `MAX_REASON_CHARS` = 200.
- Readers: API (`list_rejects`).
- Pruned by `retention.prune_older_than` (rows of old files).

### `bucket_objects`

- Purpose: marks of bucket objects that the bucket reader already copied. It survives a restart and is shared by workers.
- Key columns: `site_id`, `mark`, `seen_at`. PK `(site_id, mark)`.
- Writers: importer bucket reader (`remember_bucket_mark`). Cleanup prunes (`prune_bucket_marks`, age = `raw_retention_days`).
- Readers: importer bucket reader (`known_bucket_marks`).

## Events

### `events`

- Purpose: one row for each request line (origin, CDN, or paired). The raw fact table.
- Partitioning: `partition by range (ts)`, one partition for each UTC day, named `events_YYYYMMDD`. Partitions are made by `ensure_events_partition(day date)` (see rule ST.1 in README.md).
- Key columns:
  - Identity: `id bigint` (identity), `site_id`, `ts`, `file_id`, `line_no`, `line_key`.
  - `source` in `origin`, `cdn`, `paired`.
  - Request: `method`, `host`, `path`, `status`, `edge_status`, `origin_status`, `bytes_sent`, `response_time_ms`, `referrer`.
  - Client: `client_ip inet`, `user_agent`, `client_key` (null = not grouped), `edge_signal` in `bot`, `human`, `none`.
  - Pairing: `request_id`, `edge_request_id`, `pair_state` in `pending`, `paired`, `single`, `cdn_bypass`, `origin_line_key`, `origin_file_id`, `imported_at`.
  - `verdict_id`: set by verify.
  - `in_views boolean`: set by activity reconstruction. `false` = new work.
- Keys and indexes:
  - PK `(site_id, ts, id)`.
  - `events_ts_brin`: BRIN on `ts`.
  - `events_client (site_id, client_key, ts)`.
  - `events_dedupe`: unique `(site_id, source, line_key, ts)`. This index drops duplicate lines.
  - `events_id (id)`, `events_file (site_id, file_id)`.
  - `events_pending (site_id, edge_request_id, ts)` where `pair_state = 'pending'`.
  - `events_no_verdict (site_id, client_key)` where `verdict_id is null and pair_state <> 'pending'`.
  - `events_not_in_views (site_id, ts)` where `not in_views and pair_state <> 'pending'`.
  - `events_origin_line_key (site_id, origin_line_key)` where `origin_line_key is not null`.
- Writers: importer (`events.copy_events`, `events.delete_file_events`, `events.delete_file_rows`), pairing (`pairing.pair_pending`, `pairing.expire_pending`), verify (`verdicts.assign_events_verdict`), activity reconstruction (`views.mark_in_views`, `views.reset_site`), cleanup (`events.drop_old_partitions`).
- Readers: pairing, verify (`pending_client_groups`), activity reconstruction, recommendations (`sample_events`, `count_events`), API (`list_events`, `get_event`, overview queries).
- The origin row is deleted when it pairs. The paired row keeps `origin_line_key` and `origin_file_id`, so a re-import of the origin file does not insert the line again.

## Verify and classify

### `verdicts`

- Purpose: verdict and traffic class for each client. Append-only. The current row is the row with the highest `id` for `(site_id, client_key, edge_signal)`.
- Key columns:
  - Client: `client_key`, `edge_signal`, `user_agent`, `client_ip`.
  - Verify: `claimed_agent`, `registry_category`, `verdict` in `VERIFIED`, `CLAIMED`, `UNVERIFIED`, `SPOOFED`, `UNKNOWN`; `method` in `ip_list`, `rdns`, `none`; `evidence`, `registry_version`, `ip_snapshot_version`, `checked_at`.
  - Classify: `traffic_class smallint` (1 to 6), `confidence` in `high`, `medium`, `low`, `rule_id`, `rule_version`, `class_evidence`, `flags text[]`, `ua_type`, `classified_at`.
- Indexes: `verdicts_current (site_id, client_key, edge_signal, id desc)`, `verdicts_unclassified (site_id, id)` where `traffic_class is null`, `verdicts_agent (site_id, claimed_agent, id desc)`.
- Writers: verify (`append_verdict`), classify (`save_classes`; `where traffic_class is null`, so a classified row is never overwritten).
- Readers: verify (`current_verdict`), classify (`fetch_unclassified`), activity reconstruction (joins on `events.verdict_id`), API.

### `ip_list_snapshots`

- Purpose: versioned copies of published bot IP lists. Verify checks a client IP against a snapshot.
- Key columns: `source`, `version`, `fetched_at`, `prefixes cidr[]`. PK `(source, version)`.
- Indexes: `ip_list_snapshots_latest (source, fetched_at desc)`.
- Writers: verify (`ip_lists.save_snapshot`; `on conflict do nothing`).
- Readers: verify (`latest_snapshot`, `latest_versions`, `ip_in_prefixes`).

## Activity reconstruction

### `sessions`, `open_sessions`

- Purpose: `sessions` = closed sessions. `open_sessions` = sessions that can still get events. `open_sessions` is made with `like sessions including all`, so it has the same columns and indexes.
- Key columns: `session_id`, `version` (counts rebuilds of the row), `client_key`, `verdict_id`, `claimed_agent`, `user_agent`, `client_ip`, `edge_signal`, `traffic_class`, `confidence`, `started`, `last_seen`, `requests`, `distinct_pages`, `pages_in_order text[]`, `key_pages_visited`, `reached_conversion`, `has_retry`, `has_loop`, `retries`, `shared_ip`, `gaps text[]`, `status_counts jsonb`, `journeys_reached jsonb`, `retry_paths text[]` (added in `0004`). PK `(site_id, session_id)`.
- Indexes: `sessions_started (site_id, started desc)`, `sessions_client (site_id, client_key, started)`, `sessions_class (site_id, traffic_class, started)`, `sessions_last_seen` and `open_sessions_last_seen` on `(site_id, last_seen)` (from `0004`).
- Writers: activity reconstruction (`views.finish_sessions`, `views.close_idle_sessions`, `views.reset_site`). Pruned by `retention.prune_older_than` (`sessions` only, on `last_seen`).
- Readers: recommendations (pattern queries), API (`list_sessions`, `get_session`).

### `session_events`

- Purpose: links a session to its events in order.
- Key columns: `site_id`, `session_id`, `event_id`, `event_ts`, `seq`. PK `(site_id, session_id, seq)`.
- Indexes: `session_events_event (site_id, event_id)`.
- Writers: activity reconstruction (`views.finish_sessions`). Readers: recommendations (`event_ids`, `sample_events`), API.

### `page_stats`

- Purpose: hourly rollup for each page and traffic class.
- Key columns: `hour`, `path`, `traffic_class`, `tags text[]`, `requests`, `sessions`, `clients`, `median_bytes`, `n_2xx`, `n_3xx`, `n_403`, `n_429`, `n_4xx`, `n_5xx`, `retries`. PK `(site_id, hour, path, traffic_class)`.
- Indexes: `page_stats_path (site_id, path, hour)`.
- Writers: activity reconstruction (`views.refresh_hours`: delete and insert for the changed hours). Readers: recommendations, API (`list_pages`, `get_page`, overview).

### `journey_steps`

- Purpose: hourly funnel rows for each journey step.
- Key columns: `hour`, `journey_id`, `traffic_class`, `step_no`, `step_path`, `sessions_reached`, `sessions_retry_or_loop`. PK `(site_id, hour, journey_id, traffic_class, step_no)`.
- Writers: activity reconstruction (`views.refresh_hours`). Readers: recommendations (`journey_funnel`), API (`list_journeys`).

### `agents`

- Purpose: hourly rollup for each claimed agent and traffic class.
- Key columns: `hour`, `claimed_agent`, `traffic_class`, `verification`, `confidence`, `first_seen`, `last_seen`, `requests`, `sessions`, `distinct_pages`, `top_paths text[]`. PK `(site_id, hour, claimed_agent, traffic_class)`.
- Writers: activity reconstruction (`views.refresh_hours`). Readers: recommendations (`agents_for_sessions`), API (`list_agents`, `get_agent`, overview).

## Recommendations

### `recommendation_runs`

- Purpose: one row for each slow-lane run of a site.
- Key columns: `id bigint` (PK), `site_id`, `window_size`, `window_start`, `window_end`, `rule_version`, `prompt_version`, `model`, `status` in `running`, `success`, `failed`, `started_at`, `finished_at`, `counts jsonb`, `error`.
- Indexes: `recommendation_runs_site (site_id, id desc)`.
- Writers: recommendations (`recommendations.create_run`, `recommendations.finish_run`). Readers: API (`latest_run`, `list_recommendation_runs`).

### `recommendations`

- Purpose: ranked items of a run.
- Key columns: `id` (PK), `run_id` (FK to `recommendation_runs`, `on delete cascade`), `stable_id`, `rank`, `pattern`, `target`, `journey_id`, `score numeric(8,1)` (changed in `0002`), `impact`, `frequency`, `severity`, `confidence_factor numeric(3,1)`, `confidence`, `factor_reasons jsonb`, `evidence jsonb`, `bundle jsonb`, `text_source` in `llm`, `template`, `change` in `new`, `open`, `gone`, plus text columns (`recommended_test`, `reason`, `potential_issue`, `suggested_validation`, `next_action`, `model`, `prompt_version`).
- Indexes: `recommendations_run (run_id, rank)`, `recommendations_stable (site_id, stable_id, run_id)`.
- Writers: recommendations (`insert_recommendations`). Readers: recommendations (`previous_items`), API (`list_recommendations`, `get_recommendation`).

### `llm_text_cache`

- Purpose: LLM text cache. Same evidence bundle = same text.
- Key columns: `bundle_hash` (PK), `site_id`, `text jsonb`, `model`, `prompt_version`, `created_at`.
- Writers: recommendations (`save_cached_text`; `on conflict (bundle_hash) do update`). Readers: recommendations (`cached_text`; matches `bundle_hash`, `site_id`, `model`, `prompt_version`).

## Pipeline

### `pipeline_runs`

- Purpose: one row for each fast-lane or slow-lane run.
- Key columns: `id uuid` (PK), `site_id`, `lane` in `fast`, `slow`, `started_at`, `finished_at`, `status` in `running`, `success`, `failed`, `failed_step`, `error`, `counts jsonb`.
- Indexes: `pipeline_runs_site (site_id, lane, started_at desc)`.
- Writers: pipeline (`runs.start_run`, `runs.finish_run`, `runs.fail_running_run`). Readers: pipeline (`consecutive_failures`, `running_runs_started_before`), alerts service, API (`runs.recent_runs`, `queries.list_pipeline_runs`, `queries.get_pipeline_run`, health route).
- Pruned by `retention.prune_older_than` (`status <> 'running'`).

### `site_work`

- Purpose: fair turns. Records when each `(site_id, lane)` is due.
- Key columns: `site_id`, `lane`, `last_run_at`, `last_success_at`, `consecutive_failures`, `next_due_at`. PK `(site_id, lane)`.
- Writers: pipeline (`work.ensure_site_work`, `work.take_due_site`, `work.record_run`, `work.release_slow`). Readers: pipeline.

### `alerts`

- Purpose: open and resolved alerts.
- Key columns: `id` (PK), `site_id`, `kind` in `no_data`, `failed_runs`, `source`, `message`, `raised_at`, `resolved_at`.
- Indexes: `alerts_open`: unique `(site_id, kind, coalesce(source, ''))` where `resolved_at is null`. One open alert for each site, kind and source.
- Writers: alerts service (`alerts.raise_alert`, `alerts.resolve_alert`). Readers: API (`alerts.list_alerts`, `queries.open_alerts`).

## SQL functions

| Function | Created in | Purpose |
|---|---|---|
| `ensure_events_partition(day date) returns text` | `0001`, replaced in `0005` | Makes the `events` partition for a UTC day and returns its name. No error when it exists. |

`drop_events_partitions_older_than(integer)` was made in `0001` and removed in `0005`. Retention now runs from Python (`events.drop_old_partitions`).

## Temporary tables

| Table | Made by | Purpose |
|---|---|---|
| `events_stage` | `events.copy_events` | Stage for `COPY`. Same columns as `events`. Truncated before and after each batch. |
| `_new`, `_dirty`, `_ungrouped`, `_hours`, `_ev0`, `_ev0r`, `_starts`, `_ev1`, `_ev`, `_sess`, `_old`, `_idmap`, `_final`, `_oldev`, `_he`, `_hflags`, `_hx` | `views.py` | Work sets inside one reconstruction transaction (`on commit drop`). |
