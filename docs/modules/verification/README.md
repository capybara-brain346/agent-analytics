# Verification

This module answers one question: "This client says it is bot X. Is that true?"
Input: events with no verdict (user agent and client IP only). Output: append-only `verdicts` rows. Each event points to one row through `events.verdict_id`.
The CDN bot score is not an input here. It is a classification input (see [classification](../classification/README.md)).

## Read this when

- You add or change a bot in the registry.
- You add a vendor IP list or change how IP lists are downloaded or stored.
- You change how a verdict is computed (IP list, rDNS, UNVERIFIED, CLAIMED, UNKNOWN).
- You change when a verdict is reused or when a new verdict row is added.
- You change the `verdicts` or `ip_list_snapshots` tables.
- You debug a wrong SPOOFED or UNVERIFIED verdict.
- You change the shared-IP ranges (`shared-ip.yaml`).

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/services/verify/service.py` | `verify_new_clients`, `reverse_dns_check`, `DnsResolver`, reuse rules (`_reusable`), one check per client key (`_check`). |
| `apps/api/src/services/verify/ip_lists.py` | `download_snapshots`, `parse_prefixes`, `ip_in_snapshot`, `latest_snapshot`. Downloads vendor IP lists. Stores a new version only when the content changes. |
| `apps/api/src/services/verify/__init__.py` | Public exports of the verify service. |
| `apps/api/src/services/verify/README.md` | Short service note. |
| `apps/api/src/services/registry/service.py` | `BotEntry`, `load_registry`, `match_user_agent`, `shared_ip_ranges`, `is_shared_ip`. Reads the YAML files again when the file changes. |
| `apps/api/src/services/registry/README.md` | Short service note. |
| `apps/api/src/store/verdicts.py` | `current_verdict`, `append_verdict`, `pending_client_groups`, `assign_events_verdict`, `verdicts_without_class`. |
| `apps/api/src/store/ip_lists.py` | `save_snapshot`, `latest_snapshot`, `latest_versions`, `ip_in_prefixes`. |
| `apps/api/src/models/keys.py` | `client_key`, `normalize_ip`. Used by import to set `events.client_key`. |
| `apps/api/config/registry/bots.yaml` | Bot registry (data). |
| `apps/api/config/registry/ip-lists/*.json` | Bundled IP lists. Used in offline mode and as first snapshot when the download fails. |
| `apps/api/config/registry/shared-ip.yaml` | Shared-IP ranges (CGN and cloud-egress). Used by activity reconstruction. |
| `apps/api/migrations/versions/0001_initial.py` | Creates `verdicts` and `ip_list_snapshots`. |
| `apps/api/src/cli.py` | CLI command `download-ip-lists`. |
| `apps/api/src/services/pipeline/service.py` | `FAST_STEPS` runs `("verify", verify.verify_new_clients)` after `pair`. |
| `apps/api/src/services/pipeline/worker.py` | `_maintenance` runs the `download_ip_lists` job one time each day. |
| `apps/api/tests/verify/test_verify.py` | Verdict, reuse and DNS tests. |
| `apps/api/tests/verify/test_ip_lists.py` | IP list parse, download and offline tests. |
| `apps/api/tests/foundation/test_registry.py` | Registry load, match and shared-IP tests. |

## Data flow

```
 events (verdict_id is null, client_key not null, pair_state <> 'pending')
    │  store.pending_client_groups: group by (client_key, edge_signal)
    ▼
 verify_new_clients
    │
    ├─► registry.match_user_agent(UA) ── no match ──► UNKNOWN / method none
    │        │ BotEntry (id, category, verify)
    │        ▼
    ├─► store.current_verdict(site, client_key, edge_signal)
    │        │  _reusable? yes ──► reuse row id (no new row)
    │        │  no
    │        ▼
    ├─► _check (one for each client_key)
    │        ├─ method ip_list ─► snapshot in memory ─ IP in prefixes ► VERIFIED
    │        │                                         not in prefixes ► SPOOFED
    │        │                    no snapshot for source ────────────► UNVERIFIED
    │        ├─ method rdns ────► PTR, then A/AAAA ─ match ───────────► VERIFIED
    │        │                                       no match/no PTR ─► SPOOFED
    │        │                    error / timeout ───────────────────► UNVERIFIED
    │        └─ method none ────────────────────────────────────────► CLAIMED
    ▼
 store.append_verdict ──► verdicts (new row)
 store.assign_events_verdict ──► events.verdict_id = row id

 IP lists (separate path, one time each day):
 vendor URL ─► download_snapshots ─► parse_prefixes ─► changed? ─► ip_list_snapshots (new version)
 bundled ip-lists/*.json ─────────────────────────────┘ (offline, or no snapshot yet)
```

Example (illustration only):

```
 #  path        UA              IP            client_key
 1  /pricing    GPTBot/1.2      20.171.1.5    A
 2  /products   GPTBot/1.2      20.171.1.5    A
 3  /about      GPTBot/1.2      20.171.1.5    A
 4  /pricing    Googlebot/2.1   45.33.9.9     B
 5  /home       Chrome/129      81.2.3.4      C

 verdicts
 key  claimed    verdict    method    evidence
 A    gptbot     VERIFIED   ip_list   "in vendor list, snapshot 2026-10-10"
 B    googlebot  SPOOFED    rdns      "45.33.9.9 -> host.linode.com, not in googlebot.com, google.com"
 C    -          UNKNOWN    none      "no bot name in UA"
```

Sequence (rDNS case):

```
 verify_new_clients      Postgres (verdicts)     DNS resolver
    │ current_verdict(site, key, signal)              │
    │────────────────────────►│                       │
    │ none or not reusable    │                       │
    │◄────────────────────────│                       │
    │ PTR 66.249.66.1                                 │
    │────────────────────────────────────────────────►│
    │ crawl-66-249-66-1.googlebot.com                 │
    │◄────────────────────────────────────────────────│
    │ A / AAAA crawl-66-249-66-1.googlebot.com        │
    │────────────────────────────────────────────────►│
    │ 66.249.66.1 (same IP: match)                    │
    │◄────────────────────────────────────────────────│
    │ append_verdict(VERIFIED, rdns)                  │
    │────────────────────────►│                       │
    │ assign_events_verdict   │                       │
    │────────────────────────►│                       │
```

Verdict rows: three cases.

```
 New event group (client_key, edge_signal)
   ├─ no row for key ─────────────────────────────► check, ADD row #1
   ├─ row exists, inputs unchanged ───────────────► REUSE current row (no new row)
   └─ row exists, an input changed ───────────────► check again, ADD row #2
      (new IP-list snapshot for its source ·         (row #1 stays; old events
       new registry or rule version ·                 keep pointing to it)
       rDNS older than 24 h)

 Mon  GPTBot 20.171.1.5 -> row #1 VERIFIED (snapshot Mon) <── events 1-40
 Tue  new snapshot without the IP
      GPTBot 20.171.1.5 -> row #2 SPOOFED  (snapshot Tue) <── events 41-60
```

## Rules and decisions

Verdict values: `VERIFIED`, `CLAIMED`, `UNVERIFIED`, `SPOOFED`, `UNKNOWN`. The `verdicts.verdict` column has a check constraint on these five values. Method values: `ip_list`, `rdns`, `none`.

| ID | Rule | Why |
|---|---|---|
| [2.1] | Verify runs as a step after import and pair in each fast-lane run. It processes only events with no verdict. | Same pattern as import. It can run again alone. |
| [2.2] | `client_key` = hash of (UA, client IP). One check for each key while inputs do not change. Results go in an append-only `verdicts` table. Events point to a verdict row (N : 1). | Millions of lines, thousands of clients. DNS calls are slow. |
| [2.3] | The client IP comes from the CDN log line (paired events) or from the real client IP in the origin log (`real_ip`). | The CDN IP would give a false SPOOFED. |
| [2.4] | The method is what the vendor publishes: IP list first (offline, fast), then rDNS. | A UA is a claim. |
| [2.5] | No signature check (RFC 9421) in the MVP. | Default logs do not contain signature headers. |
| [2.6] | A DNS error or timeout gives UNVERIFIED, not SPOOFED. | A failed check is not proof of a lie. |
| [2.7] | A UA with no registry match gives UNKNOWN (method `none`). No new detection method. | Undeclared bots are an unsolved problem. Be honest. |
| [2.8] | Verdicts are append-only. Each check ADDS a row. Never upsert or overwrite. Each event points to the row that was current at its time. | Analytics must keep history. A verdict that was true on Monday stays true for Monday's events (auditability). |
| [2.8a] | Same key and unchanged inputs: reuse the current row. Check again (new row) only when: the IP-list snapshot version of the entry's source changes, the registry version changes, the classify rule version changes, or an rDNS result is older than `rdns_ttl_hours`. | Same inputs give the same answer. rDNS is a slow network call. |
| [2.8b] | The worker downloads vendor IP lists one time each day (new snapshot version only when the content changes). | A stale list keeps a stale verdict forever. |
| [2.9] | Each row stores verdict, method, evidence text, registry version, IP snapshot version and `checked_at`. | Auditability. |
| [2.10] | The registry is YAML (`config/registry/bots.yaml`), built from arcjet/well-known-bots and ai.robots.txt. | A new bot must not change pipeline code. |
| [V.1] | The row key is `(site_id, client_key, edge_signal)`. `edge_signal` (`bot`, `human`, `none`) only splits rows. One check serves all rows of one `client_key`. | Classification needs one row for each edge signal. The identity check does not depend on the edge signal. |
| [V.2] | The current row is the row with the highest `id` for the row key. | Append-only: the newest row wins. |
| [V.3] | `client_key` is NULL when UA or IP is missing or invalid. Such events are not grouped and get no verdict. | There is no "who" to verify. |
| [V.4] | `client_key` uses the normalized IP: IPv6 becomes its `/64` network, an IPv4-mapped IPv6 address becomes IPv4. | A client rotates addresses inside one `/64`. |
| [V.5] | An rDNS result with verdict UNVERIFIED is not reused after `unverified_retry_minutes`. Retry it early. | A DNS error is not a final answer. |
| [V.6] | rDNS check: PTR names must end in one of the registry `suffixes`. The forward lookup (A and AAAA) of that name must return the client IP. No PTR name gives SPOOFED. | Forward-confirmed reverse DNS. A PTR record alone is easy to fake. |
| [V.7] | `method: ip_list` with no stored snapshot for the source gives UNVERIFIED (evidence "no IP list snapshot"). | The list is not available. It is not proof of a lie. |
| [V.8] | Evidence text for `ip_list` contains the snapshot version. | A wrong SPOOFED on an old log is visible. |
| [V.9] | `verdict = SPOOFED` sets `flags = ['spoofed']`. | Other modules read the flag. |
| [V.10] | A bot with `method: none` gives CLAIMED. | The vendor publishes no method. |
| [V.11] | Bots can share one IP-list source. ClaudeBot, Claude-User and Claude-SearchBot all use `anthropic.json`. | Anthropic publishes one list and no reverse DNS names. An IP match proves "from Anthropic", not which of the three bots. |
| [V.12] | DNS calls run concurrently. `DNS_CONCURRENCY = 20` in `verify/service.py`. Each check has a timeout of `dns_timeout_seconds * 2`. | Bound the load on the resolver and the run time. |
| [V.13] | The registry matches a UA by case-insensitive substring of `ua_pattern`. With `regex: true`, it is a case-insensitive regular expression. The longest pattern wins, so list order does not matter. | Predictable matches. |
| [V.14] | Verify sets the identity columns of a verdict row. Classification sets `traffic_class`, `confidence`, `rule_id`, `class_evidence`, `ua_type` and `classified_at` on the same row. | One row for each "who" and time. See [classification](../classification/README.md). |
| [V.15] | A rule-version change (classify `RULE_VERSION`) adds new verdict rows. A row with `rule_version` NULL is still reusable. | Classification must fill new rows (NULL = not set yet). |

### IP list refresh and storage

- `download_snapshots` reads all registry entries with `method: ip_list` and a `source`. It makes one source list (`source` to `url`).
- Online with a `url`: it downloads the JSON. On failure it keeps the old snapshot. Only when no snapshot exists yet does it use the bundled file in `ip_list_dir`.
- Offline (`offline = true`) or no `url`: it reads the bundled file from `ip_list_dir`.
- `parse_prefixes` accepts the Google style `{"prefixes": [{"ipv4Prefix": ...}, {"ipv6Prefix": ...}]}` and a plain list of CIDRs. A list item can also be a dict with `cidr`. An unknown format or an empty result raises `ValueError`.
- The snapshot is stored only when the sorted prefixes differ from the latest snapshot.
- `version` = date of the list (`creationTime` in the payload, else the file date for bundled files, else today). If this version exists with other content, the version becomes `<date>-<6 hex of sha256>`.
- A failure for one source is logged (`ip list <source> not updated`) and counted in `failed`. The other sources continue.
- The worker runs `download_ip_lists` through `_maintenance`. It runs one time each day (`MAINTENANCE_EVERY = 1 day`). If the job raises, it runs again after `MAINTENANCE_RETRY = 1 hour`. The job is not scheduled in offline mode.
- Run it by hand: `uv run python -m src.cli download-ip-lists` (in offline mode it loads the bundled files).

### Bot registry entry (data, not code)

```yaml
- id: gptbot
  vendor: OpenAI
  ua_pattern: "GPTBot"
  category: ai_crawler
  verify: { method: ip_list, source: openai-gptbot.json, url: "https://openai.com/gptbot.json" }
- id: googlebot
  vendor: Google
  ua_pattern: "Googlebot"
  category: search_crawler
  verify: { method: rdns, suffixes: [googlebot.com, google.com] }
```

- `category`: `search_crawler`, `ai_crawler`, `agent_client`, `other_bot`, `automation_tool`. `automation_tool` = scripted HTTP clients and CLI tools (curl, python-requests).
- `verify` forms: `{ method: ip_list, source, url }`, `{ method: rdns, suffixes }`, `{ method: none }`. A missing `verify` means `{ method: none }`.
- `version` in `bots.yaml` is the registry version. It is stored in each verdict row. A change gives new rows.

## Configuration

Settings are in `apps/api/src/config/settings.py`. Set them with environment variables of the same name in upper case.

| Setting | Default | Effect |
|---|---|---|
| `rdns_ttl_hours` | `24` | An rDNS verdict older than this is checked again (new row). |
| `unverified_retry_minutes` | `60` | An rDNS UNVERIFIED verdict is checked again after this time. |
| `dns_timeout_seconds` | `2.0` | DNS resolver timeout and lifetime. The whole check times out at twice this value. |
| `ip_list_dir` | `apps/api/config/registry/ip-lists` | Folder of bundled IP-list files. |
| `offline` | `False` | No downloads. IP lists load from `ip_list_dir`. The daily download job is not scheduled. |
| `config_dir` | `apps/api/config` | Parent of `registry/`. Registry files are in `<config_dir>/registry/`. |
| `DNS_CONCURRENCY` (constant, `verify/service.py`) | `20` | Maximum parallel rDNS checks. |
| `MAINTENANCE_EVERY` (constant, `pipeline/worker.py`) | 1 day | Interval of the IP list download job. |
| `MAINTENANCE_RETRY` (constant, `pipeline/worker.py`) | 1 hour | Retry interval after the job raises. |

YAML data:

| File | Key | Effect |
|---|---|---|
| `bots.yaml` | `version` | Registry version. A change adds new verdict rows. |
| `bots.yaml` | `bots[].id`, `vendor`, `ua_pattern`, `category`, `verify`, `regex` | Bot entry. See above. |
| `shared-ip.yaml` | `version`, `ranges[].name`, `ranges[].cidr` | Extra shared-IP ranges. `100.64.0.0/10` (CGN) is always shared (built in `registry/service.py`). |

## Interfaces

Python (import from `src.services.verify`, `src.services.registry`, `src.store`):

| Name | Signature / use |
|---|---|
| `verify.verify_new_clients` | `async (conn, site_id, now=None, resolver=None) -> dict`. Returns counts `groups`, `events`, `reused`, `new_rows`, `checks`. The pipeline step `verify`. `now` and `resolver` are injected by tests. |
| `verify.download_snapshots` | `async (conn=None, client=None) -> dict`. Returns counts `sources`, `new`, `unchanged`, `failed`. Opens its own connection when `conn` is None. |
| `verify.reverse_dns_check` | `async (ip, suffixes, resolver) -> (verdict, evidence)`. Raises on DNS error. |
| `verify.DnsResolver` | `DnsResolver(timeout)`. Methods `ptr(ip)`, `addresses(host)`. A `Resolver` protocol with these two methods lets tests inject a fake. |
| `verify.parse_prefixes`, `verify.ip_in_snapshot`, `verify.latest_snapshot` | See `ip_lists.py`. |
| `registry.load_registry` | `() -> (version, list[BotEntry])`. |
| `registry.match_user_agent` | `(user_agent, entries=None) -> BotEntry | None`. |
| `registry.BotEntry` | Frozen dataclass: `id`, `vendor`, `ua_pattern`, `category`, `verify`, `is_regex`. |
| `registry.is_shared_ip`, `registry.shared_ip_ranges` | Shared-IP test. Used by activity reconstruction. |
| `verdicts.current_verdict` | `async (conn, site_id, client_key, edge_signal) -> dict | None`. |
| `verdicts.append_verdict` | `async (conn, row) -> int` (new id). Writes only columns in `VERDICT_COLUMNS`. |
| `verdicts.pending_client_groups` | `async (conn, site_id) -> list[dict]`. |
| `verdicts.assign_events_verdict` | `async (conn, site_id, client_key, edge_signal, verdict_id, min_ts, max_ts) -> int`. The `ts` bounds let Postgres prune daily partitions. |
| `verdicts.verdicts_without_class` | `async (conn, site_id) -> list[dict]`. |
| `ip_lists.save_snapshot` | `async (conn, source, version, prefixes) -> bool`. False when `(source, version)` exists. |
| `ip_lists.latest_snapshot`, `ip_lists.latest_versions` | Latest snapshot for a source. Map of source to latest version. |
| `ip_lists.ip_in_prefixes` | `async (conn, source, version, ip) -> bool`. SQL prefix test. |

Tables:

| Table | Columns that verify writes |
|---|---|
| `verdicts` | `site_id`, `client_key`, `edge_signal`, `user_agent`, `client_ip`, `claimed_agent`, `registry_category`, `verdict`, `method`, `evidence`, `registry_version`, `ip_snapshot_version`, `rule_version`, `checked_at`, `flags`. Index `verdicts_current (site_id, client_key, edge_signal, id desc)`. |
| `ip_list_snapshots` | `source`, `version`, `fetched_at`, `prefixes cidr[]`. Primary key `(source, version)`. |
| `events` | `verdict_id` (set by verify). |

CLI: `uv run python -m src.cli download-ip-lists`. Pipeline: `uv run python -m src.cli run-pipeline fast --site <site>` runs verify as step 3.

The dashboard reads verdicts through the agents API (`apps/api/src/routes/agents.py`: `VERIFICATIONS` filter and `verification_note` text). See [api](../api/README.md).

## Known limits

- IP lists change over time. The MVP uses the latest snapshot and writes its date in the evidence, so a wrong SPOOFED on an old log is visible. Matching each event to the snapshot of its own date is later work.
- Bots that publish no method stay CLAIMED. Undeclared bots stay UNKNOWN.
- No signature check (RFC 9421). Default logs do not contain the headers.
- An Anthropic IP-list match proves "from Anthropic", not which Anthropic bot.
- For an IPv6 client, the check uses one IP from the group (`min(host(client_ip))`) of the `/64` key.
- The verdict is as good as the client IP in the log. With origin logs only, nginx must log the real client IP (`real_ip` with `set_real_ip_from <CDN ranges>`). Without it the CDN IP gives a false SPOOFED. See [ingestion](../ingestion/README.md).

## Open questions

- None open from the design. The IP-list snapshot by event date is later work (see Known limits).

## How to change

Add a new bot:

1. Add an entry in `apps/api/config/registry/bots.yaml` (`id`, `vendor`, `ua_pattern`, `category`, `verify`). No code change.
2. Choose `verify` from what the vendor publishes: `ip_list` (with `source` file name and `url`), `rdns` (with `suffixes`) or `none`.
3. For `ip_list`: put a bundled copy of the list in `apps/api/config/registry/ip-lists/<source>` (used offline and when the first download fails). If bots share one list, use the same `source` and `url`.
4. Change `version` in `bots.yaml`. A new version gives new verdict rows, so the new entry applies to clients seen before.
5. Add a match case to `apps/api/tests/foundation/test_registry.py`. Add a verdict case to `apps/api/tests/verify/test_verify.py` only if the verify method is new.
6. The `ua_pattern` is a substring. Use `regex: true` for a regular expression. Check that no longer pattern matches the same UA first.

Add or change a vendor IP list:

1. Set `source` and `url` in the entry. `test_ip_list_entries_have_https_url_and_json_source` requires an `https` URL and a `.json` source.
2. Make sure the format is a Google-style `prefixes` list or a plain CIDR list. Other formats need a change in `parse_prefixes` and a case in `tests/verify/test_ip_lists.py`.

Add a new verify method:

1. Add a branch in `_check` (`verify/service.py`) that returns `_result(verdict, method, evidence, snapshot)`.
2. Add the method name to the `verdicts.method` check constraint in a new Alembic migration (`apps/api/migrations/versions/`).
3. Add reuse conditions in `_reusable` if the result can expire.
4. Add tests in `tests/verify/test_verify.py`.
5. Update this document.

Change a reuse rule: edit `_reusable` in `verify/service.py`. Add one test in `tests/verify/test_verify.py`.

## Tests

Tests need Postgres on port 55432 (see `apps/api/README.md`). Run from `apps/api`:

```
uv run pytest tests/verify
uv run pytest tests/foundation/test_registry.py
```

| File | Covers |
|---|---|
| `tests/verify/test_verify.py` | IP list VERIFIED and SPOOFED, no snapshot, UNKNOWN and CLAIMED, shared Anthropic list, rDNS VERIFIED, SPOOFED, error, timeout, DNS concurrency cap, reuse without a new row, new row on snapshot, registry and classify rule version change, rDNS TTL, UNVERIFIED retry, `edge_signal` split with one check, pending and ungrouped events, other site untouched, idempotency. |
| `tests/verify/test_ip_lists.py` | Prefix formats, `ip_in_snapshot`, store once and version on change, download failure keeps the old snapshot, bundled fallback, offline load. |
| `tests/foundation/test_registry.py` | Default registry load, UA match, case, no match, longest pattern, regex, custom registry dir, shared-IP ranges, https URL and json source of IP-list entries. |

## Related modules

- [ingestion](../ingestion/README.md): sets `client_ip`, `client_key` and `edge_signal` on events.
- [pairing](../pairing/README.md): runs before verify. Pending pair rows are skipped.
- [classification](../classification/README.md): reads verdict rows, fills the class columns.
- [activity-reconstruction](../activity-reconstruction/README.md): reads the registry category and the shared-IP ranges.
- [pipeline](../pipeline/README.md): runs verify as a fast-lane step and the daily IP list download.
- [store](../store/README.md): tables and migrations.
- [api](../api/README.md): agents routes that show verification.
