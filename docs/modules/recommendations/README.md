# Recommendations

The recommendation engine is the slow lane of the pipeline. It answers: "Which journeys should Webzero test next, and why?"
Input: session, page, journey and agent tables (see [activity-reconstruction](../activity-reconstruction/README.md)) and the site config YAML.
Output: one append-only run with a ranked list of recommendations. Each recommendation has 8 fields. Code owns every fact. An optional LLM writes 4 text fields.

## Read this when

- You change a pattern query (P1 to P5), a threshold or the score formula.
- You change the recommendation text, the text validator or the LLM client.
- You change the LLM provider, model or prompt version.
- You change a site config key (`key_pages`, `conversion_pages`, `journeys`, `access_policy`, `site_pages`).
- You change how runs are stored, compared (new, open, gone) or listed.
- You change `POST /api/recommendations/generate` ("Generate now") or `run-recommendations`.
- You change the window size or how often the slow lane runs.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/services/recommendations/service.py` | `generate`, `find_candidates`, `build_bundle`, `parse_window`, `stable_id`, `bundle_hash`, `RULE_VERSION`. |
| `apps/api/src/services/recommendations/scoring.py` | Score formula, factor values, `SEVERITY`, `CONFIDENCE_FACTOR`, factor reason texts. |
| `apps/api/src/services/recommendations/text.py` | `template_text`, `recommended_test`, `validate_llm_text`, `TEXT_FIELDS`, `class_name`. |
| `apps/api/src/services/recommendations/llm.py` | `OpenRouterClient`, `default_client`, `SYSTEM_PROMPT`, `parse_text`, `LLMError`. |
| `apps/api/src/services/recommendations/README.md` | Short module note next to the code. |
| `apps/api/src/services/site_config/service.py` | `load_site_config`, `SiteConfig`, `Journey`, `AccessPolicy`, `list_sites`. |
| `apps/api/src/services/site_config/README.md` | Short module note next to the code. |
| `apps/api/src/store/recommendations.py` | All SQL of the engine: 5 pattern queries, fact bundle queries, run and recommendation writes, text cache. |
| `apps/api/src/store/queries.py` | Read queries for the API: `latest_run`, `previous_run_id`, `run_change_counts`, `list_recommendation_runs`, `list_recommendations`, `get_recommendation`. |
| `apps/api/src/routes/recommendations.py` | HTTP endpoints under `/api/recommendations`. |
| `apps/api/src/models/api.py` | Response models (`RunHeader`, `RecommendationItem`, `RecommendationDetail`, `GenerateResult`), `PATTERN_NAMES`. |
| `apps/api/src/models/domain.py` | `Pattern` enum (`P1` to `P5`). |
| `apps/api/src/services/pipeline/service.py` | `run_recommendations`, `_slow_steps`, `slow_interval`: lock, run row, call to `generate`. |
| `apps/api/src/services/pipeline/worker.py` | Slow loop that starts a run for each due site. |
| `apps/api/src/cli.py` | CLI command `run-recommendations`. |
| `apps/api/config/sites/example.yaml` | Example site config with all recommendation keys. |
| `apps/api/config/sites/piyushc.yaml` | Site config of the live test site (CDN source only). |
| `apps/api/config/sites/piyushc-pages.txt` | `site_pages` file for pattern P4 of the live test site. |
| `apps/api/migrations/versions/0001_initial.py` | Tables `recommendation_runs`, `recommendations`, `llm_text_cache`. |
| `apps/api/migrations/versions/0002_integration.py` | `recommendations.score` becomes `numeric(8, 1)`. |
| `apps/api/tests/recommendations/` | Tests: `test_patterns.py`, `test_generate.py`, `helpers.py` (`FakeLLM`, `blocked_page`), `conftest.py`. |

## Data flow

Funnel. The LLM never sees the raw data.

```
 ~5,000,000 log lines ─► events ─► ~200,000 sessions ─► views (SQL)
        ─► 5 pattern queries ─► ~20 candidates ◄── LLM works ONLY here
```

(The numbers are an order-of-magnitude example, not a measure.)

Run data flow.

```
 sessions + open_sessions · page_stats · journey_steps · agents ──┐   (tables: activity-reconstruction)
 config/sites/<site>.yaml: key_pages, conversion_pages,           │
   journeys, access_policy, site_pages ───────────────────────────┤
                                                                  ▼
 1 find_candidates: 5 pattern queries (one SQL each, store/recommendations.py)
        │ candidate = pattern · target · session IDs · counts · confidence counts
        ▼
 2 scoring.factors: SCORE = Impact × Frequency × Severity × Confidence        (code)
        ▼  sort: score desc, sessions_count desc, pattern, target; rank = 1..n
 3 build_bundle: FACT BUNDLE from SQL, exact                                  (code)
        ▼
 4 _write_text:
     llm is None ─────────────────────────────────────────────► template_text
     llm_text_cache hit (site, bundle hash, model, prompt) ────► cached text
     llm.write_text(bundle) ─► validate_llm_text ─ pass ─► text + save in cache
                                                 └ fail / error ─► template_text
        ▼
 5 compare with the previous successful run: new / open / gone
        ▼
 6 insert recommendations (append-only) + finish_run(counts)
        ▼
 recommendation_runs, recommendations ─► /api/recommendations ─► dashboard
```

"Generate now" sequence.

```
 Dashboard      API route            pipeline.service         recommendations.generate     Postgres
    │ POST /api/recommendations/generate?site=S&window=6h        │                           │
    │──────────────►│                      │                     │                           │
    │               │ run_recommendations(S, window)             │                           │
    │               │─────────────────────►│ take site+slow lock │                           │
    │               │                      │────────────────────────────────────────────────►│
    │               │                      │ lock taken ◄────────────────────────────────────│
    │ 409 lock_taken│◄─ LockTaken ─────────│  (stop)             │                           │
    │               │                      │ lock free: _execute (one transaction per step)  │
    │               │                      │────────────────────►│ create_run, candidates,   │
    │               │                      │                     │ text, insert, finish_run  │
    │               │                      │                     │──────────────────────────►│
    │               │                      │◄──── run_id ────────│                           │
    │               │ latest_run + run_header                    │                           │
    │ 200 completed │◄─────────────────────│                     │                           │
    │ 500 run_failed ◄── RunFailed / any error (old list stays valid)                         │
```

## Rules and decisions

Decision IDs `[5.x]` come from the original design. Other rules (`R...`) describe the code.

### Schedule and runs

- `[5.5]` Production: one run every 2 weeks on a 14-day window. MVP: 6-hour window, one run every 6 hours, plus on demand (CLI and button). The window is a setting (`RECOMMENDATION_WINDOW`). Each run is stored.
  Why: recommendations are not real-time and not eager (team decision).
- `[5.4]` Runs are append-only and carry `rule_version` (`RULE_VERSION = "1"`). The stable ID is `sha256("pattern|target|journey_id")[:16]` (`stable_id`). The UI shows new, still open or gone against the previous successful run.
  Why: evidence stays valid after a PM acts.
- R1. Views still update after each import (fast lane) for the dashboard. Recommendations are a separate command: `run-recommendations --window 14d`.
  Why: the slow lane must not slow down the fast lane.
- R2. The window runs from `now - window` to `now`. `window_end` is `now`. `generate` accepts an injected `now`. Window format: `<n>m`, `<n>h` or `<n>d` (`parse_window`). `0` and other formats raise `ValueError`.
  Why: tests need a fixed time.
- R3. `generate` runs inside one transaction (pipeline step). A failed run leaves no `recommendation_runs` row and no `recommendations` rows. The previous list stays valid.
  Why: a half-written list must never show.
- R4. `change` values: `new` (stable ID not in the previous successful run), `open` (in the previous run), `gone` (in the previous run, not in this run). A `gone` item is a copy of the old item stored in the new run with `rank = NULL`. A `gone` item is not `open` in the run after.
  Why: history rule and a clean comparison.
- R5. The previous run is the latest run of the site with `status = 'success'` and a smaller ID (`previous_items`, `previous_run_id`).
  Why: only finished runs count.

### Inputs

- `[5.3]` Inputs: site config (written by a person), access policy, `site_pages` (sitemap or content list).
  Why: logs cannot tell which pages matter or which blocks are intended.
- R6. `access_policy` has three path-prefix lists: `allow`, `block`, `robots_disallow`. `blocked_by_intent(path)` is true when the longest matching prefix in `block` + `robots_disallow` is longer than the longest matching prefix in `allow`. A path with no match counts as not blocked. The query string is ignored.
  Why: the longest rule wins, like in robots.txt.
- R7. A key page is a page in `key_pages` or `conversion_pages`. Both lists are in the key set.
  Why: impact and P2 use one definition of "key".

### Patterns (PDF section 04)

- `[5.1]` All 5 patterns. P4 compares the customer sitemap or content list with fetches. The engine does no page-content check and does not fetch pages.
  Why: we capture, we do not diagnose content.
- R8. Evidence for all patterns: pattern query, then session IDs, then `session_events`, then `events` (exact log lines). Session IDs are capped at `ID_CAP = 5000` for each candidate (`store/recommendations.py`). The count is always exact.
  Why: every claim links to exact log lines.
- R9. Pattern queries read the sessions in the window from `sessions` and `open_sessions` (`last_seen >= start`). Hourly tables (`page_stats`, `journey_steps`, `agents`) are read from the UTC hour of `start`.
  Why: closed and open sessions both count. Hourly rows have hour resolution.

| Pattern | Name (`PATTERN_NAMES`) | Rule | Target | Severity |
|---|---|---|---|---|
| P1 | Product discovery | Sessions of class 2 or 4 with `key_pages_visited >= P1_MIN_KEY_PAGES` and not `reached_conversion`. One candidate for the site. | First `conversion_pages` entry, or `conversion` if the list is empty | 2 |
| P2 | Blocked access | `page_stats` of class 1 or 2 on a key page with `n_403 + n_429 >= P2_MIN_BLOCKS`, and the access policy does not block the path by intent. | The page | 3 |
| P3 | Broken navigation | Distinct sessions of class 2 or 4 with a retry or loop at a journey step (`retry_paths`) and the journey reached (`journeys_reached`), count `>= P3_MIN_SESSIONS`. | The journey step path | 3 |
| P4 | Content discoverability | Each `site_pages` URL against `page_stats` of class 2 (AI crawlers) and class 5 (browsers). Kinds below. Runs only if `site_pages` is not empty and class 2 has at least one request in the window. | The URL | 2 |
| P5 | Full-journey simulation | Critical journey (at least 2 steps): step 1 reached by class 2 or 4 sessions, last step reached by none. | Last step of the journey | 2 |

P4 kinds (column `kind`):

| Kind | Rule |
|---|---|
| `never_fetched` | Class 2 made 0 requests to the URL. |
| `blocked_or_redirected` | Class 2 got no 2xx and at least one 403 or 3xx. |
| `small_response` | Class 2 got 2xx and its median bytes are below `P4_BYTES_RATIO` × the browser median bytes (label: Inferred). |

- R10. P1 is "product to conversion": the candidate `paths` are all `key_pages`. P3 and P5 take a `journey_id`. P2 and P4 take no journey. P3 and P4 are key only if the path is in the key set. P1, P2 and P5 are always key.
  Why: the impact factor needs this flag.
- `[5.2]` Thresholds (3 pages, 5 × 403/429, 3 sessions), the P4 bytes ratio and the frequency buckets are in config. Tune them on demo data.
  Why: a 6 h window has far fewer sessions than 14 days.

### Score (each factor is visible in the UI)

```
 Impact     key / conversion page = 3 · other = 1
 Frequency  sessions affected: < 5 = 1 · 5-50 = 2 · > 50 = 3
 Severity   P2, P3 = 3 · P1, P4, P5 = 2                      (fixed per pattern: SEVERITY)
 Confidence most evidence sessions decide: high 1.0 · medium 0.6 · low 0.3
 Example: P2 on /pricing = 3 × 2 × 3 × 1.0 = 18
```

- R11. Confidence label = the level with most evidence sessions (`confidence_label`). A tie goes to the lower level. No sessions = low. Session counts are by `sessions.confidence`: `high`, `medium`, and everything else (including NULL) is low.
  Why: a weak claim must not look strong.
- R12. `confidence_factor` meaning (`CONFIDENCE_WHY`): high = verified identity, IP not shared. Medium = claimed identity or browser, IP not shared. Low = agent client, shared IP, or unknown class.
  Why: the UI shows the reason for each factor (`factor_reasons`).
- R13. Score is stored with one decimal (`recommendations.score numeric(8, 1)`, migration 0002). Example: 3 × 2 × 3 × 0.6 = 10.8.
  Why: the stored score must equal the formula.
- R14. Frequency buckets: `< FREQUENCY_MID_MIN` = 1, `FREQUENCY_MID_MIN` to `FREQUENCY_HIGH_OVER` = 2, `> FREQUENCY_HIGH_OVER` = 3 (`frequency_factor`).
  Why: buckets are config, not code.

### Fact bundle (what the LLM reads)

The bundle (`build_bundle`) holds:

| Key | Content |
|---|---|
| `pattern`, `target`, `journey_id`, `kind`, `step_no`, `paths`, `window` | Candidate identity and window. |
| `sessions_count`, `events_count` | Exact counts. |
| `class_status` | Status counts for each traffic class on the target paths, with `class_name`. |
| `agents` | Up to 10 agents with class, verification and sessions. |
| `time_pattern` | `first_seen`, `last_seen`, `peak_hours_utc` (top 3). |
| `access_policy` | Path, `blocked_by_intent`, `allow`, `block`, `robots_disallow`. |
| `journey_position`, `journey_funnel` | Journeys that contain the target, step number, sessions reached and sessions with retry or loop for each step (class 2 and 4). |
| `related` | Other candidates of the same journey (pattern, target, score). |
| `samples` | Up to 5 sample events with IDs. Failed (status >= 400) and target-path events come first. |
| `thresholds` | Thresholds and frequency settings used. |

### The 8 recommendation fields

| Field | Filled by |
|---|---|
| Recommended test (`recommended_test`) | code (`text.recommended_test`, from target and journey) |
| Reason (`reason`) | LLM from the bundle, else template. Label `observed`. |
| Evidence (`evidence`) | code (session IDs and event IDs, with counts) |
| Potential issue (`potential_issue`) | LLM, else template. Label `inferred`. |
| Suggested validation (`suggested_validation`) | LLM, else template. Label `inferred`. |
| Priority (`score`, `impact`, `frequency`, `severity`, `confidence_factor`, `factor_reasons`) | code |
| Confidence (`confidence`) | code |
| Next action (`next_action`) | LLM, else template. Label `unknown`. |

- `[5.6]` Each recommendation states its Unknown part and why simulation is needed. Every template `next_action` has an "Unknown:" sentence. The LLM prompt asks for the same.
  Why: PDF section 04.

### Text: LLM and templates

- `[5.7]` The LLM writes only `reason`, `potential_issue`, `suggested_validation` and `next_action` (`TEXT_FIELDS`). Code fills the rest.
  Why: facts can never be invented. Long-term: richer, case-specific text than templates.
- `[5.8]` Validator (`validate_llm_text`). All 4 fields must be non-empty strings. Then:
  - Every path in the text must also be in the bundle.
  - A bot registry name must not appear in the text unless it is in the bundle `agents`.
  - Every number in the text must be a bundle fact, or one of `2`, `3`, `403`, `429` (status words). Numbers in the bundle keys `id`, `ts`, `class`, `first_seen`, `last_seen`, `session_ids`, `event_ids` do not count as facts.
  - Fail: use template text.
  Why: catch hallucinations.
- `[5.9]` Template text (`template_text`) is the fallback when the LLM is off, fails, returns bad JSON or fails the validator. The win condition never depends on the LLM.
  Why: reliability.
- `[5.10]` LLM text is cached in `llm_text_cache`. The cache key is `sha256(bundle JSON, sorted keys)` (`bundle_hash`). A hit needs the same site, model and prompt version. Model and prompt version are stored with the text and with the recommendation (`model`, `prompt_version`, only when `text_source = 'llm'`).
  Why: same facts give the same text, low cost, auditability.
- R15. `text_source` is `llm` or `template`. Run counts store `text_llm`, `text_template` and `cache_hits`. A cache hit counts as `llm`.
  Why: the UI shows a "Template text" marker and the run shows how many items used the LLM.
- R16. The LLM sees the fact bundle only, never raw events. The system prompt (`SYSTEM_PROMPT`) tells it to use only bundle facts, to return only a JSON object with the 4 keys, and to state the Unknown part and why a simulation with a real agent is needed.
  Why: code owns every fact.
- R17. No LLM client = no LLM. `default_client` returns `None` if `OPENROUTER_API_KEY` is not set, or if `LLM_MODEL` is not set (a warning is logged in the second case).
  Why: LLM is optional. No vendor is needed for a run.
- R18. The LLM client does no retry (`NO_RETRY`) and sends `max_tokens=1024`, `response_format={"type": "json_object"}`, `stream=False`. Any error (`LLMError`, any exception) becomes template text for that item only.
  Why: one bad call must not fail the run.

## Configuration

Settings are in `apps/api/src/config/settings.py`. Environment variable names are the field names in upper case.

| Setting (env var) | Default | Effect |
|---|---|---|
| `recommendation_window` (`RECOMMENDATION_WINDOW`) | `6h` | Window of the scheduled slow lane, and of `run-recommendations` without `--window`. Also sets the slow lane interval (`<n>h` or `<n>d`; other formats fall back to 6 h). |
| `p1_min_key_pages` | `3` | P1: key pages a session must visit. |
| `p2_min_blocks` | `5` | P2: minimum `n_403 + n_429`. |
| `p3_min_sessions` | `3` | P3: minimum sessions with a retry or loop. |
| `frequency_mid_min` | `5` | Frequency 1 below this value. |
| `frequency_high_over` | `50` | Frequency 3 above this value. |
| `p4_bytes_ratio` | `0.3` | P4: AI median bytes below this share of the browser median = `small_response`. |
| `openrouter_api_key` (`OPENROUTER_API_KEY`) | `None` | LLM API key. `None` = template text only. |
| `llm_base_url` (`LLM_BASE_URL`) | `https://openrouter.ai/api/v1` | OpenRouter or a compatible gateway. |
| `llm_model` (`LLM_MODEL`) | `None` | OpenRouter model ID, for example `anthropic/claude-sonnet-5.5`. `None` = template text only. |
| `llm_prompt_version` (`LLM_PROMPT_VERSION`) | `1` | Part of the cache key. Stored with each LLM text and in the run. Change it when you change `SYSTEM_PROMPT`. |
| `llm_timeout_seconds` (`LLM_TIMEOUT_SECONDS`) | `30.0` | Timeout of one LLM call. |
| `no_data_alert_minutes` | `60` | Default for the site key of the same name (not used by this module). |

Helm: `llm.model` and `llm.baseURL` in `deploy/helm/agent-analytics/values.yaml`. `OPENROUTER_API_KEY` goes in the secret `existingSecret`. Compose: `OPENROUTER_API_KEY` and `LLM_MODEL` in `deploy/compose/.env.example` (commented out).

Site config keys read by this module (`config/sites/<site_id>.yaml`):

| Key | Default | Effect |
|---|---|---|
| `key_pages` | `[]` | Key page paths. P1 counts them. They are in the key set (impact 3, P2 pages). |
| `conversion_pages` | `[]` | Conversion pages. In the key set. The first entry is the P1 target. |
| `journeys` | `[]` | List of `{id, steps: [paths], critical: bool}`. `critical` defaults to `false`. P5 uses critical journeys with 2 or more steps. |
| `access_policy.allow` | `[]` | Path prefixes that are allowed on purpose. |
| `access_policy.block` | `[]` | Path prefixes blocked on purpose. |
| `access_policy.robots_disallow` | `[]` | Path prefixes of robots.txt `Disallow` (written by hand in the YAML). |
| `site_pages` | `[]` | Key content for P4. An inline list, or a file name (`site_pages: file.txt` or `site_pages: {file: file.txt}`) relative to the YAML folder. One URL or path for each line. Empty lines and `#` lines are skipped. A full URL is cut to path and query. |

Other site keys (`site_id`, `sources`, `cdn_field_map`, `request_id_header`, `ingest_token_sha256`, `no_data_alert_minutes`, `cdn_bucket`) belong to [ingestion](../ingestion/README.md) and [pairing](../pairing/README.md).

## Interfaces

Python:

| Name | Signature | Notes |
|---|---|---|
| `generate` | `async generate(conn, site_id, window, now=None, llm=None) -> int` | Writes one run. Returns the run ID. Raises `SiteNotFound` (no YAML) or `ValueError` (bad window). `llm=None` uses `default_client(settings)`. Any object with `.model` and `async write_text(bundle) -> dict` works as `llm`. |
| `parse_window` | `parse_window(window: str) -> timedelta` | Formats `30m`, `6h`, `14d`. |
| `score` | `score(impact, frequency, severity, confidence) -> float` | The formula. |
| `template_text` | `template_text(pattern, bundle) -> dict` | Fallback text with the 4 `TEXT_FIELDS`. |
| `validate_llm_text` | `validate_llm_text(text, bundle) -> bool` | Rule `[5.8]`. |
| `load_site_config` | `load_site_config(site_id) -> SiteConfig` | Raises `SiteNotFound` if the file is missing or the ID is invalid (`^[a-z0-9][a-z0-9._-]*$`). |
| `list_sites` | `list_sites() -> list[str]` | The site list = the `*.yaml` files in `config/sites/`. |
| `pipeline.run_recommendations` | `async run_recommendations(site_id, window, pool=None) -> str` | Takes the site + slow lane lock. Raises `LockTaken` or `RunFailed`. |

CLI (from `apps/api`):

| Command | Effect |
|---|---|
| `uv run python -m src.cli run-recommendations --site S [--window 6h]` | One recommendation run now. Exit 1 on lock taken or failure. |
| `uv run python -m src.cli run-pipeline slow --site S` | The slow lane through `run_lane` (window = `RECOMMENDATION_WINDOW`). |

HTTP (all under `/api`, query `site` is optional when one site exists):

| Endpoint | Effect |
|---|---|
| `GET /api/recommendations` | Latest successful run (or `run=<id>`). Filters: `pattern` (`P1` to `P5`), `confidence` (`high`, `medium`, `low`), `change` (`new`, `open`, `gone`). Returns `run`, `empty_reason` (`no_run`, `no_candidates` or `null`), `items`, `gone`. |
| `GET /api/recommendations/runs` | Runs of the site, newest first, paged. Each has window, versions, model, counts, `compared_with_run_id`, `error`. |
| `POST /api/recommendations/generate?window=6h` | "Generate now". `window` matches `^\d+[hd]$`, default `6h`. `200` with `status: completed` and the run header. `409 lock_taken` if a pipeline run is active. `500 run_failed` on error. |
| `GET /api/recommendations/{rec_id}` | Detail: the 8 fields with labels (`observed`, `inferred`, `unknown`), `fact_bundle`, `history` over runs, `first_seen_run_id`, `related`, `text_source_note`, run header. |

Tables (see [store](../store/README.md)):

| Table | Content |
|---|---|
| `recommendation_runs` | One row per run: `site_id`, `window_size`, `window_start`, `window_end`, `rule_version`, `prompt_version`, `model`, `status` (`running`, `success`, `failed`), `started_at`, `finished_at`, `counts` (jsonb), `error`. |
| `recommendations` | One row per item per run: `run_id`, `stable_id`, `rank`, `pattern`, `target`, `journey_id`, score columns, text columns, `evidence` (jsonb: `sessions`, `events`), `text_source`, `model`, `prompt_version`, `change`, `bundle` (jsonb). Index on `(run_id, rank)` and `(site_id, stable_id, run_id)`. |
| `llm_text_cache` | `bundle_hash` (primary key), `site_id`, `text`, `model`, `prompt_version`, `created_at`. |

Run `counts` keys: `candidates`, `new`, `open`, `gone`, `by_pattern`, `text_llm`, `text_template`, `cache_hits`.

The dashboard screens that use these endpoints are in [dashboard](../dashboard/README.md).

## Known limits

- The LLM layer sees the bundle only. It cannot find new patterns.
- P1 gives one candidate for each site, with the first conversion page as target. If `conversion_pages` is empty, the target is `conversion`.
- `site_pages` P4 is off if `site_pages` is empty or class 2 has no request in the window.
- `access_policy.robots_disallow` is a hand-written list. The engine does not fetch `robots.txt`.
- The `llm_text_cache` key is `bundle_hash` alone. A new model or prompt version for the same bundle replaces the old cache row.
- Hourly tables are read from the start of the UTC hour of the window start. Counts from `page_stats` can include up to 1 hour before the window. Session tables use the exact window start.
- The 14-day production window has not been tested against real traffic. Thresholds are tuned on demo data only.
- Logs show requests and status codes only. Every recommendation has an Unknown part that only a simulation with a real agent can fill.

## Open questions

- None recorded.

## Out of scope and roadmap

Out of scope: AI page-content check, AI site-config suggestion.
Roadmap: the LLM reads the ~50 most common journey shapes (SQL) and proposes new patterns.

## How to change

| Change | Steps |
|---|---|
| Change a threshold or frequency bucket | Edit the default in `apps/api/src/config/settings.py`. Update the table above. Run `uv run pytest tests/recommendations`. |
| Add a pattern `P6` | Add the SQL in `store/recommendations.py`. Call it in `find_candidates`. Add the value to `Pattern` (`models/domain.py`), `SEVERITY` (`scoring.py`), `PATTERN_NAMES` (`models/api.py`), `recommended_test` and `template_text` (`text.py`), and the route filter regex `^P[1-5]$` (`routes/recommendations.py`). Add a positive and a negative test in `test_patterns.py`. Raise `RULE_VERSION`. Update this doc and the dashboard. |
| Change the score formula or factor values | Edit `scoring.py`. Raise `RULE_VERSION`. Update `test_score_example` and the example in this doc. |
| Change the prompt | Edit `SYSTEM_PROMPT` in `llm.py`. Raise `LLM_PROMPT_VERSION` so the cache is not reused. |
| Change the LLM provider or model | Set `LLM_BASE_URL` and `LLM_MODEL` (a compatible gateway needs no code change). A different API shape needs a new client class with `model` and `write_text(bundle)`. Pass it to `generate`. |
| Change template text | Edit `template_text` in `text.py`. Run `test_template_passes_validator`. |
| Add a field to the fact bundle | Add it in `build_bundle`. Check the validator: new numbers are now allowed as facts. |
| Add a key page, journey or policy for a site | Edit `config/sites/<site_id>.yaml`. No code change. |
| Change the window or run frequency | Set `RECOMMENDATION_WINDOW` (for example `14d`). The slow lane interval follows. |

Rules: keep SQL in `store/recommendations.py`. Keep config values in `settings.py`.

## Tests

From `apps/api` (needs Postgres on port 55432, see `apps/api/README.md`):

```
uv run pytest tests/recommendations
```

| File | Covers |
|---|---|
| `tests/recommendations/test_patterns.py` | `parse_window`, P1 to P5 positive and negative cases, P3 distinct sessions. |
| `tests/recommendations/test_generate.py` | Score example, P2 `/pricing` = 18, bundle contents, validator, template fallback, LLM text and cache, new/open/gone, LLM HTTP client, `default_client`, fractional score, P4 ratio setting. |
| `tests/e2e/test_pipeline_e2e.py` | Full path from ingest to recommendations and API. |

## Related modules

- [activity-reconstruction](../activity-reconstruction/README.md): sessions, journeys and page stats that the patterns read.
- [classification](../classification/README.md): traffic classes 1 to 6 and session confidence.
- [verification](../verification/README.md): bot registry (agent names in the validator) and verification state.
- [pipeline](../pipeline/README.md): slow lane, lock, worker loop, run rows.
- [store](../store/README.md): tables and migrations.
- [api](../api/README.md): HTTP conventions, auth, errors.
- [dashboard](../dashboard/README.md): Recommendations screen and "Generate now" button.
- [ingestion](../ingestion/README.md) and [pairing](../pairing/README.md): other site config keys.
