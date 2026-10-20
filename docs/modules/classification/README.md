# Classification

Classification puts each client into one of 6 traffic classes. It uses deterministic rules in a fixed order. There is no ML.
Input: new verdict rows with no class (from verification) and the UA of each row. Output: class, confidence, rule ID, rule version and evidence on the same verdict row.

## Read this when

- You change a traffic class name, number or rule.
- You change how confidence is set.
- You change the UA parser (`ua_type`).
- You change how the CDN bot score becomes an edge signal (`bot` / `human` / `none`).
- You change when a verdict row is reused or added (the three cases).
- You show a class name in the API or the dashboard.

## Code map

| Path | Purpose |
|---|---|
| `apps/api/src/services/classify/rules.py` | `classify()`, `Classification`, `RULE_VERSION`. Ordered rules. Pure function. |
| `apps/api/src/services/classify/ua.py` | `ua_type()`. Regex and `ua_parser` UA type. |
| `apps/api/src/services/classify/service.py` | `classify_new_verdicts()`. Reads unclassified rows, saves classes. |
| `apps/api/src/services/classify/__init__.py` | Public exports. |
| `apps/api/src/services/classify/README.md` | Short code-level note. |
| `apps/api/src/store/classify.py` | SQL for the class columns of `verdicts`. |
| `apps/api/src/store/verdicts.py` | Verdict row insert, current row, event assignment (verify side of the three cases). |
| `apps/api/src/services/verify/service.py` | `_reusable()` decides reuse or new row. Reads `RULE_VERSION`. |
| `apps/api/src/services/importer/adapters/cdn.py` | `_edge_signal()`. Turns the vendor bot score into `bot` / `human` / `none`. |
| `apps/api/config/cdn/example.yaml` | Example CDN field map with the `edge_bot` block. |
| `apps/api/config/cdn/cloudflare.yaml` | Cloudflare Pages field map. No `edge_bot` block. |
| `apps/api/config/registry/bots.yaml` | Bot registry. Gives `registry_category`. |
| `apps/api/src/models/domain.py` | Enums `TrafficClass`, `Confidence`, `EdgeSignal`, `UaType`, `RegistryCategory`, `Verdict`. |
| `apps/api/src/models/api.py` | `CLASS_NAMES`. Class number to display name for the API. |
| `apps/api/src/routes/events.py` | Event detail returns the `classification` object. |
| `apps/api/migrations/versions/0001_initial.py` | Creates table `verdicts` and its class columns. |
| `apps/dashboard/src/lib/classes.ts` | Dashboard class names and colors. Names must match the table in this doc. |
| `apps/api/tests/classify/` | Unit tests: `test_rules.py`, `test_ua.py`, `test_service.py`. |

## Data flow

```
 CDN log line ──(bot score column)──▶ importer/adapters/cdn.py
   field map `edge_bot.column`           _edge_signal()  ──▶ events.edge_signal
   `edge_bot.bot_below`                                       (bot | human | none)
                                                                   │
 events (user_agent, client_ip, edge_signal)                       ▼
   │                                              verify_new_clients()
   │  group by (client_key, edge_signal)          match registry ─▶ claimed_agent,
   └────────────────────────────────────────────▶ registry_category, verdict
                                                       │ append row (traffic_class NULL)
                                                       ▼
                                                 verdicts table
                                                       │ fetch_unclassified()
                                                       ▼
        user_agent ─▶ ua_type() ─▶ ua_type ─┐
        verdict ────────────────────────────┤
        registry_category ──────────────────┼─▶ classify() ─▶ Classification
        edge_signal ────────────────────────┘     (class, confidence, rule_id,
                                                   evidence, flags)
                                                       │ save_classes()
                                                       ▼
                                 verdicts: traffic_class, confidence, rule_id,
                                 rule_version, class_evidence, ua_type, flags,
                                 classified_at
                                                       │
                                                       ▼
                                 reconstruction (sessions), API, dashboard
```

```
 worker          verify           classify         store (verdicts)
   │ fast lane      │                 │                  │
   │──verify_new_clients()──▶         │                  │
   │                │──append_verdict (class NULL)──────▶│
   │                │──assign_events_verdict────────────▶│
   │◀──counts───────│                 │                  │
   │──classify_new_verdicts()────────▶│                  │
   │                │                 │──fetch_unclassified──▶│
   │                │                 │◀──rows (class NULL)───│
   │                │                 │ ua_type() + classify() for each row
   │                │                 │──save_classes (WHERE traffic_class IS NULL)──▶│
   │◀──{"classified": n}──────────────│                  │
```

Step order in `FAST_STEPS` (`apps/api/src/services/pipeline/service.py`): `import`, `pair`, `verify`, `classify`, `views`.

## Rules and decisions

### The 6 classes

The numbers and names are fixed. The API (`CLASS_NAMES`) and the dashboard (`classes.ts`) use these names.

| # | Name | `TrafficClass` member |
|---|---|---|
| 1 | Verified search crawler | `VERIFIED_SEARCH_CRAWLER` |
| 2 | Known AI crawler | `KNOWN_AI_CRAWLER` |
| 3 | Other identifiable bot | `OTHER_IDENTIFIABLE_BOT` |
| 4 | Browser automation / agent-like | `BROWSER_AUTOMATION` |
| 5 | Ordinary browser | `ORDINARY_BROWSER` |
| 6 | Unknown | `UNKNOWN` |

### Verdict and confidence names

The same names are used in the API, the database and the dashboard.

```
 Verdict:     VERIFIED · CLAIMED · UNVERIFIED · SPOOFED · UNKNOWN
 Confidence:  High · Medium · Low        (stored lower case: high | medium | low)
```

### Inputs for each client

| Input | From | Values |
|---|---|---|
| Verdict | Verification | `VERIFIED`, `CLAIMED`, `UNVERIFIED`, `SPOOFED`, `UNKNOWN` |
| Registry category | Bot registry (`bots.yaml`) | `search_crawler`, `ai_crawler`, `agent_client`, `other_bot`, `automation_tool`, or none |
| UA type | `ua_type()` | `browser`, `headless`, `library`, `bot`, `other` |
| Edge bot signal | CDN log, through the field map, if the CDN has one | `bot`, `human`, `none` |

### Ordered rules (first match wins)

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

Rule IDs in `rules.py` (stored in `verdicts.rule_id`):

| Order | Rule ID | Condition | Class | Evidence text |
|---|---|---|---|---|
| 1 | `R1-spoofed` | verdict is `SPOOFED` | 6 | claims a known bot, failed verification (spoofed). Flag `spoofed`. |
| 2 | `R2-search-verified` | category `search_crawler` and verdict `VERIFIED` | 1 | search crawler, verified |
| 3 | `R3-search-unverified` | category `search_crawler`, verdict not `VERIFIED` | 3 | claims search crawler, unverified |
| 4 | `R4-ai-agent` | category `ai_crawler` or `agent_client` | 2 | AI crawler or agent client, `<verdict>` |
| 5 | `R5-other-bot` | category `other_bot` or `automation_tool` | 3 | `<category>` in registry |
| 6 | `R5-library-ua` | UA type `library` | 3 | library user agent |
| 7 | `R5-other-bot` | UA type `bot` | 3 | bot words in user agent |
| 8 | `R6-automation` | UA type `headless` | 4 | headless browser user agent |
| 9 | `R6-automation` | UA type `browser` and edge `bot` | 4 | browser UA, CDN flags it as bot |
| 10 | `R7-browser-human` | UA type `browser` and edge `human` | 5 | browser UA, CDN says human |
| 11 | `R8-unknown` | UA type `browser`, edge `none` | 6 | browser UA, not confirmed human |
| 12 | `R8-unknown` | everything else | 6 | no identifying signal |

### Confidence

```
 VERIFIED ───────────────► High
 CLAIMED / edge signal ──► Medium
 UNVERIFIED / UA only ───► Low
```

Code (`_confidence()` in `rules.py`): verdict `VERIFIED` gives high. Verdict `CLAIMED`, or edge signal `bot` or `human`, gives medium. All other cases give low. The confidence does not depend on the rule that matched.

### UA parsing (`ua_type()`)

Checks run in this order. The first match wins.

| Order | Test | Result |
|---|---|---|
| 1 | UA is empty, `None` or `-` | `other` |
| 2 | Regex `HEADLESS` (headless, phantomjs, puppeteer, playwright, selenium, webdriver) | `headless` |
| 3 | Regex `LIBRARY` (python-requests, python-urllib, curl, wget, go-http-client, axios, node-fetch, okhttp, `Java/`, libwww, httpx, aiohttp, scrapy) | `library` |
| 4 | Regex `BOT` (`bot` word end, `bot/`, crawler, spider, crawl, slurp) | `bot` |
| 5 | `ua_parser` family is in `BROWSER_FAMILIES` (chrome, firefox, safari, edge, opera, and others) | `browser` |
| 6 | Anything else | `other` |

### Decisions

- [3.1] Classify one time for each (`client_key`, edge bot signal). Why: the key must contain every rule input. The edge signal has 3 values only.
- [3.2] The CDN field map converts the vendor bot score to `bot` / `human` / `none`. The threshold (`bot_below`) is in the YAML file. Score below the threshold = `bot`. Score at or above = `human`. Missing or not a number = `none`. Why: vendors use different scales. Code stays neutral.
- [3.3] Bot names are YAML data. Rule order is code, with `RULE_VERSION`. Why: a new bot needs no code change. The logic stays testable.
- [3.4] Class, confidence, rule ID, rule version and evidence are stored on the same append-only verdict row as verification (decision [2.8]). No overwrite. `save_classes()` updates only rows with `traffic_class IS NULL`. Why: auditability. History is kept.
- [3.5] Agent clients (for example ChatGPT-User) go to class 2. Why: they declare themselves. Class 4 is for activity found only from evidence.
- [3.6] Browser UA with no edge signal goes to class 6 UNKNOWN, not class 5. Dashboard text: "browser UA, not confirmed human". Why: a UA is a claim. Be honest.
- [3.7] No subtypes in the output. Activity reconstruction reads the registry category (`agent_client`) for the 2-minute session gap (`agent_session_gap_minutes`). Why: 6 classes are enough. The category is already registry data.
- No ML. Output is the 6 top-level classes only. Why: rules are auditable and need no training data.
- A spoofed verdict also has flag `spoofed`. Verification sets the flag when it adds the row. Classification adds the flag again and removes duplicates. Why: the flag stays on the row even if the class rule changes.
- The `classification` object in the event detail API has `label: "inferred"`. Why: a class is an inference, not an observation.

### Verdict rows: three cases (verify + classify)

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

The key is (`site_id`, `client_key`, `edge_signal`). The current row is the row with the highest `id` for the key. `_reusable()` in `verify/service.py` returns false (new row) when one of these is true:

- No current row exists.
- `registry_version` changed.
- `rule_version` of the current row is not `NULL` and not `RULE_VERSION`. A new row lets classify fill the class with the new rules.
- The row has method `rdns`, verdict `UNVERIFIED` and is older than `unverified_retry_minutes`. A DNS error is not a final answer.
- The registry method is `ip_list` and `ip_snapshot_version` is not the newest snapshot.
- The row has method `rdns` and is older than `rdns_ttl_hours`.

The old row stays. Old events keep their `verdict_id`.

## Configuration

Classification has no setting in `apps/api/src/config/settings.py`. The values below control it from other places.

| Name | Default | Effect |
|---|---|---|
| `RULE_VERSION` (`services/classify/rules.py`) | `"1"` | Stored in `verdicts.rule_version`. A change makes verification add new rows. Change it when a rule changes. |
| `edge_bot.column` (CDN YAML) | none (block is optional) | CDN log column with the vendor bot score. |
| `edge_bot.bot_below` (CDN YAML) | `30` in `example.yaml` | Score below this value = `bot`. At or above = `human`. |
| `rdns_ttl_hours` | `24` | Age after which verification checks an rDNS verdict again. This adds a row. |
| `unverified_retry_minutes` | `60` | Age after which verification retries an rDNS `UNVERIFIED` verdict. |
| `agent_session_gap_minutes` | `2` | Session gap for clients of category `agent_client` (set by decision [3.7]). |
| `HEADLESS`, `LIBRARY`, `BOT`, `BROWSER_FAMILIES` (`services/classify/ua.py`) | see file | UA type patterns. They are code constants. |

## Interfaces

| Name | Signature / shape | Used by |
|---|---|---|
| `classify` | `classify(verdict: str, registry_category: str \| None, ua_type: str, edge_signal: str) -> Classification` | `classify_new_verdicts`, tests |
| `Classification` | frozen dataclass: `traffic_class: int`, `confidence: str`, `rule_id: str`, `evidence: str`, `flags: list[str]` | `service.py` |
| `RULE_VERSION` | `str` | `service.py`, `verify/service.py` |
| `ua_type` | `ua_type(user_agent: str \| None) -> UaType` | `service.py` |
| `classify_new_verdicts` | `async (conn: AsyncConnection, site_id: str) -> dict` returns `{"classified": n}` | Pipeline step `classify` (`FAST_STEPS`) |
| `fetch_unclassified` | `async (conn, site_id) -> list[dict]` (`id, user_agent, registry_category, verdict, edge_signal`) | `service.py` |
| `save_classes` | `async (conn, rows: list[tuple]) -> int`. Row = `(traffic_class, confidence, rule_id, rule_version, class_evidence, ua_type, flags, id)` | `service.py` |
| `CLASS_NAMES` | `dict[int, str]` in `src/models/api.py` | `routes/events.py`, `routes/overview.py` |

Table `verdicts` (class columns): `traffic_class` (smallint, check 1 to 6, `NULL` = not classified), `confidence` (`high` / `medium` / `low`), `rule_id`, `rule_version`, `class_evidence`, `ua_type`, `flags` (text array), `classified_at`. Index `verdicts_unclassified` covers rows where `traffic_class IS NULL`.

API: the event detail response (`GET` event by id in `routes/events.py`) has `classification` with `traffic_class`, `class_name`, `confidence`, `rule_id`, `rule_version`, `inputs` (`verdict`, `registry_category`, `ua_type`, `edge_signal`), `evidence`, `label`. It is `null` when the row has no class.

## Known limits

- On a site with origin logs only, almost all human traffic is UNKNOWN (no edge signal, so rule `R8-unknown`).
- Undeclared bots that look like browsers are UNKNOWN unless the CDN gives a bot signal.
- The Cloudflare Pages field map has no `edge_bot` block (no Bot Management). All its events have edge signal `none`.
- A UA that matches the `BOT` regex but is not in the registry goes to class 3. Its confidence is low unless the edge signal is `bot` or `human`.
- A class is set one time for each verdict row. A new `RULE_VERSION` does not reclassify old rows. Verification adds new rows for clients that appear again.

## Open questions

None.

## How to change

| Task | Steps |
|---|---|
| Add a bot or change its category | Edit `apps/api/config/registry/bots.yaml`. No code change. See [verification](../verification/README.md). |
| Change a rule or add a rule | Edit `classify()` in `rules.py`. Add a row to `TABLE` in `tests/classify/test_rules.py`. Increase `RULE_VERSION`. Update the rule table in this doc. |
| Change confidence | Edit `_confidence()` in `rules.py`. Update `TABLE` in `test_rules.py`. Increase `RULE_VERSION`. |
| Add a UA pattern | Edit the regex in `ua.py`. Add a case to `CASES` in `tests/classify/test_ua.py`. |
| Add a CDN bot signal | Add the `edge_bot` block to the CDN YAML in `apps/api/config/cdn/`. No code change. |
| Rename a class | Edit `CLASS_NAMES` (`src/models/api.py`), `classMeta` (`apps/dashboard/src/lib/classes.ts`) and the class table in this doc. |
| Add a 7th class | Change `TrafficClass`, the `verdicts.traffic_class` check (new migration), `CLASS_NAMES`, `classes.ts` and this doc. Ask first: it changes the output contract. |

## Tests

| File | Covers |
|---|---|
| `apps/api/tests/classify/test_rules.py` | Rule table: verdict, category, UA type, edge signal to class, confidence, rule ID. Spoofed flag. Evidence text. |
| `apps/api/tests/classify/test_ua.py` | `ua_type()` for browsers, headless, libraries, bots, empty UA. |
| `apps/api/tests/classify/test_service.py` | `classify_new_verdicts`: fills `NULL` rows, never overwrites, ignores other sites. |

Run from `apps/api` (needs Postgres on port 55432, see `apps/api/README.md`):

```
uv run pytest tests/classify
```

## Related modules

- [verification](../verification/README.md): gives the verdict, registry category and the verdict row.
- [pairing](../pairing/README.md): CDN field maps and the edge signal on events.
- [activity-reconstruction](../activity-reconstruction/README.md): uses the class and the `agent_client` category for sessions.
- [pipeline](../pipeline/README.md): runs the `classify` step in the fast lane.
- [store](../store/README.md): table `verdicts`.
- [api](../api/README.md): event detail and class names in responses.
- [dashboard](../dashboard/README.md): shows class names and colors.
