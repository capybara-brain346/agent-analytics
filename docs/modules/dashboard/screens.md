# Dashboard screens

Per-screen spec of the dashboard. Content, structure and behaviour only. No colours or fonts (see `apps/dashboard/src/app/styles/`). Module overview, code map, rules `[R1]` to `[R8]` and `[D1]` to `[D10]`: [README.md](README.md).

## Users

| User | Goal | Main screens |
|---|---|---|
| Product manager (primary) | Decide which journeys to test next. Trust the reason. | Recommendations, Overview, Pages & journeys |
| Engineer | Check that data arrives and the pipeline works. Debug a verdict. | Data & pipeline, Activity |
| AI agent or script | Read the same data without the UI (the product is agent-first). | JSON API with the same filters and IDs as each screen ([../api/README.md](../api/README.md)) |

## Navigation map

The side rail has three groups. The label in the rail is the label in the code (`shell/nav-config.ts`).

```
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ TOP BAR      Agent Analytics / <screen> · freshness chip · Label guide      │
 │ FILTER BAR   site · time range (1h 6h 24h 7d) · traffic classes · window     │
 └──────────────────────────────────────────────────────────────────────────────┘
   Monitor
     ├── Overview (/overview, landing) ─────────► Recommendation / Page sheets, Events
     └── Recommendations ───────────────────────► Recommendation sheet ──► Session / Event sheets
   Explore
     ├── Agents ────────────────────────────────► Agent sheet ───────────► Session sheet, Events
     ├── Activity (/events | /sessions) ────────► Event sheet ◄──► Session sheet
     └── Pages & journeys (/pages | /journeys) ─► Page sheet / Journey sheet ──► Sessions
   Manage
     └── Data & pipeline (/data) ───────────────► Import sheet · Pipeline run sheet
```

All roads end at the same two evidence sheets: **Session detail** and **Event detail**.
A detail sheet opens over the screen. It keeps the URL parameter `detail=<type>:<id>`. Sheet types: `recommendation`, `agent`, `session`, `event`, `page`, `journey`, `run`, `import`, `legend`.
The sheet shows "Back to <previous sheet>" when the user came from another sheet. Browser Back and Forward move along the same list of sheets. Close leaves the sheet the way it was opened, so Back does not reopen it.
A URL such as `/recommendations/12` opens the list with sheet `recommendation:12`. Direct routes exist for `recommendations`, `agents`, `events`, `sessions`, `journeys`. Other sheets use `?detail=`.
An unknown first path segment shows "This page does not exist." and a link to Overview.

## Global elements

### Filter bar (all screens)

| Element | Behaviour |
|---|---|
| Site selector | One site at a time. Lists the sites of `GET /api/sites` (one for each file in `apps/api/config/sites`). A URL without `site` is replaced by the first site (`router.replace`). No request goes out without a site. Changing the site keeps the other filters. With no site configured, the screen says "No site is configured. Add a file to config/sites." |
| Time range | Buttons `1h`, `6h`, `24h`, `7d`. Default `24h`. URL parameter `range`. An unknown value uses the default. The window caption shows the real window in UTC (from the overview answer). |
| Traffic classes | Multi-select of the six classes ([../classification/README.md](../classification/README.md)). No selection means all. Selecting all six clears the parameter. URL parameter `class` (comma list of class numbers). Has a Reset button. |
| Window caption | "Oct 16, 13:05–14:05 UTC". Shown at the right of the filter bar. |

A change of a filter removes the `detail` parameter (the sheet closes).

### Top bar and rail

| Element | Behaviour |
|---|---|
| Breadcrumb | "Agent Analytics / <screen name>". |
| Freshness chip | State chip from `overview.freshness.state`. Hover text (`title`) is the API `freshness.text`. Click opens Data & pipeline (the Health & alerts tab when the state is not `ok`). See "Freshness states". |
| Label guide | Button. Opens the legend sheet (`detail=legend:labels`): Observed, Inferred, Unknown, the six classes (each links to Events with that class), and the rule that a claim is not verified until VERIFIED and that HTTP 200 is not a task outcome. |
| Rail foot | "Data up to <time> UTC" from `freshness.data_up_to`. |
| Status row (page foot) | Site, "data up to <date time>" or "data freshness unknown", "all times UTC". |
| Skip link | "Skip to content" for keyboard users. |
| Mobile | The rail opens in a left sheet from the menu button. |

One overview request feeds the chip, the rail foot, the status row and the Overview screen. If this request fails, the chip shows "Data unavailable".

### Freshness states

Source: `freshness.state` from the API (derived from `pipeline_runs` and alerts, see [../pipeline/README.md](../pipeline/README.md)).

```
 API state         Chip label        Meaning (API text in the chip tooltip)
 ───────────────── ───────────────── ─────────────────────────────────────────────────────
 ok                Live              "Data up to 14:05"
 updating          Updating          "Updating… (data up to 14:00)"  - a run is in progress
 no_runs           No runs yet       no pipeline run for the site
 last_run_failed   Last run failed   "Data up to 13:55 · last run failed at Verify"
 alert_failing     Alert failing     "ALERT: pipeline failing since 13:40"  (3 failures in a row)
 alert_no_data     No recent data    "ALERT: no new logs from <site> since 12:58"  (> 1 h)
 (no answer)       Data unavailable  the overview request failed
 (loading)         Checking
```

`freshness` also holds `data_up_to`, `last_import_at`, `latest_run_id`, `failed_step`, `consecutive_failures`. The Overview coverage panel uses `last_import_at`.

## Screen 1: Overview (`/overview`, landing page)

Question: "What is happening on this site, and what needs attention?"

Content, top to bottom:

```
 [Key numbers]            Total requests · AI and automated share · Distinct agents ·
                          Error rate · Denial rate
                          each: value · change vs prior window · "No prior window" if none
                          value null -> Gap "Unknown"
 [Recommended next tests] top 3 open items of the latest run (API sends 3; "gone" skipped)
                          each: rank · target · pattern · New / Still open · priority · confidence
                          link "All recommendations"
 [Request volume]         stacked bars: requests per hour (or per day for 7d), one colour per class
                          Observed; legend links to Events by class
 [Top pages by agent      top 10 paths by agent requests (classes 1-4): agent requests · errors · denied
  traffic]                Observed; link "All pages"
 [Traffic by class]       share bar + one row per class (6): count · share · High / Medium / Low counts
                          Inferred; note for requests with no class yet; link "How classes work"
 [What the data can show] coverage panel (below)
```

Coverage panel (honest limits, always on Overview). Fields come from `overview.coverage`:

| Row | Content |
|---|---|
| CDN logs, Origin logs | One row per configured source: "Present" or "No data". |
| Paired CDN and origin | `paired_share_pct` (whole percent), or Gap "Unknown" when null. |
| Unknown class | `unknown_share_pct` as a link to Events with class 6, or Gap "No requests". |
| Blind spots | `cannot_see` text list (for example task completion), tag "Not in logs". "None" if empty. |
| Partial | One row for each `partial` text (for example browser traffic without edge signal), tag "Partial". |
| Log delivery | Only when freshness is not `ok`: "Last file <time>" or "No files". |

Interactions (`[R2]`):

| Click | Goes to |
|---|---|
| Total requests | Events (current filters) |
| AI and automated share | Events with `class=1,2,3,4` (a class filter in the URL replaces it) |
| Distinct agents | Agents |
| Error rate | Events with `status=4xx,5xx` |
| Denial rate | Events with `status=403,429` |
| A class name, count, or share bar segment | Events with `class=<n>` |
| A High / Medium / Low count | Events with `class=<n>&confidence=<level>` |
| A chart legend entry | Events with `class=<n>` |
| A top page (name) | Page sheet |
| A top-page number | Events with `path=` (and `status=` for errors and denied) and the agent classes |
| A recommendation | Recommendation sheet |
| "Unknown class" share | Events with `class=6` |

Chart bars are not links. A bucket with no request shows as a real zero.

Empty state: "No data for this site in this time range." + "Try a longer time range, or check that logs arrive." + link "Last import <time> UTC · View data sources" (or "No import yet · View data sources") to Data & pipeline.
Top pages empty: "No agent requests to pages." (text depends on whether classes 1 to 4 are selected). Recommendations empty: "No open recommendations".

## Screen 2: Recommendations (`/recommendations`)

Question: "Which journeys should we test next, and why?" This is the centrepiece.
The list ignores the time range. It follows `site` and the selected run.

### Toolbar and run header

```
 [All | New | Still open]  [Pattern ▾]  [Confidence ▾]  [Run ▾]            [Generate now]
 notice (generation state)  ·  notice (latest run failed)
 Strip:  Recommendations <n> (Run #14) · New · Still open · Gone ("Absent since run #13" / "No earlier run to compare")
 List panel  "Journeys to test"      Inferred
 Panel "Gone since the previous run"  (only when the run has gone items)
 Panel "Run history"
 Footer: Run #14 · <window> window · Rule v3 · Prompt v2 · Model <name> | "none (template text)" · Created <time>
```

| Control | URL parameter | Values |
|---|---|---|
| Status | `status` | empty (all), `New`, `Still open` (sent to the API as `change=new|open`). "Gone" has no filter. Gone items are always in their own panel. |
| Pattern | `pattern` | `P1` Product discovery, `P2` Blocked access, `P3` Broken navigation, `P4` Content discoverability, `P5` Full-journey simulation. Rules for each pattern: [../recommendations/README.md](../recommendations/README.md). |
| Confidence | `confidence` | `high`, `medium`, `low` |
| Run | `run` | empty = latest run. A number shows that run as it was (append-only). The select lists up to 50 runs. |

### "Generate now" button

```
 Click ──► POST recommendations/generate?site=
   ├─ ok          ──► notice "Run #N completed. The list shows the new run." · list and run history reload · `run` filter cleared
   ├─ 409 lock    ──► "Another run is active" + API text "A pipeline run is active. Try again in a few minutes."
   └─ 500 failed  ──► "Could not generate recommendations" + API text (run, failed step, error). "The previous list is still valid."
 While running: button "Running…" and disabled · notice "A run is active. The previous list stays visible until it ends."
```

The window of the run is the API default (6 h). The UI does not send a window.

### List columns

| Column | Content |
|---|---|
| Recommended test | `recommended_test` (or `target`). Subline: `#rank · pattern name · N events · New / Still open`. |
| Status | New or Still open, or a dash. |
| Priority | Score. Sorted by priority (no sort control). The factors are in the sheet. |
| Confidence | High, Medium, Low. |
| Sessions | Count of evidence sessions. |

A row opens the Recommendation sheet.

### Recommendation sheet (`recommendation:<id>`)

Sections in order. The eight recommendation fields map to the sections as follows.

```
 Header         status pill · confidence · recommended test · pattern · run #
 Gone note      (gone items only) "Absent in run #N. The evidence is from the last run that had it.
                Gone does not prove that the issue is fixed."
 Fields         Priority (score) · Formula · Evidence ("12 sessions · 40 requests") · Window ·
                History ("First seen in run #11 · runs #11, #12 ...")
 Priority factors   Impact / Frequency / Severity / Confidence: value + "why"          [Inferred]
 Why test this      reason text                                  [label from API: Observed]
 Potential issue    text                                         [Inferred]
 Suggested validation  text
 Evidence to inspect   session IDs and request IDs (5 shown, "Show all N", max 50 of each) -> Session / Event sheets   [Observed]
 Related            other recommendations on the same journey -> Recommendation sheet
 Suggested next step   text (includes the Unknown part and why a simulation is needed)   [Unknown]
 Fact bundle        expandable list: the exact facts given to the text writer
 Footer             text source note ("Written by LLM (model, prompt v2), checked against facts" or
                    "Template text ...") · Rule v · prompt v · model
```

A text field with no stored text shows Gap "No text stored." `[R7]`: the priority factors and the fact bundle make the score auditable. The text source note comes from the API (`text_source_note`).

### Run history

Table: run (`#id`, tags "Latest" and "Shown", window and rule version) · status · New · Still open · Gone · created. A run row does not open anything. Use the Run select to view an older run.

### Empty states

- No run yet: "No recommendation run yet" + "Generate now".
- Run with 0 candidates: "This run found no journeys to test" + "Run again". Thresholds are in `apps/api/config` and settings ([../recommendations/README.md](../recommendations/README.md)).
- Filters too narrow: "No recommendations match these filters" + "Clear filters".
- A run that did not finish shows the notice "Run #N did not complete." with the stored error.

## Screen 3: Agents (`/agents`)

Question: "Who is visiting?"

Toolbar: search (`q`, agent name), Verification select (`verdict`: Verified, Claimed, Unverified, Spoofed, Unknown). The global class filter also applies. The toolbar shows "N agent groups".

Metric strip: Agent groups · Verified identities · Claims only · Requests (all counted from the list).

List columns:

| Column | Content |
|---|---|
| Agent | Name from the registry. Subline: vendor and verification note when VERIFIED, else the note. A client with no bot name shows "Unknown (browser UA)" or "Unknown (<kind> UA)" and "No bot name · identity unknown". |
| Verification | Pill: Verified, Claimed, Unverified, Spoofed, Unknown. Colour is never the only signal. `[R3]` |
| Requests | Link to Events with `agent=<id>`. Sorted by requests. |
| Traffic class | Full class name. |
| Last seen | Time. |
| Sessions | Link to Sessions with `agent=<id>`. |

One agent name can appear in more than one row, one for each traffic class. Row key is agent ID plus class.
Footnote: "A user agent is a claim, not proof. Browser requests without an edge signal stay unknown."

### Agent sheet (`agent:<agent_id>`)

The sheet uses the page filters except `class`.

```
 Header           name · vendor/note · verification pill · class · confidence
 Activity         Observed: requests (link) · sessions (link) · distinct pages
                  vendor · first seen · last seen · requests per hour bars
                  top paths (each -> Events with agent + path) · status mix (each -> Events with agent + status)
 Why this class   Inferred: class · rule ID · identity input · registry category · UA type ·
                  edge signal · evidence · versions (rule vX · registry vY)
 Verdict history  Observed: newest first. Each row: time · verdict · method · evidence text ·
                  link "Inspect requests with this verdict" -> Events with verdict_id
                  none: "No identity check is recorded for this agent. The identity stays a claim."
 Client keys      Observed: client key · user agent · client IP · shared-IP flag
                  ("Yes · one address may hold more than one agent")
 Sessions         up to the list in the API answer -> Session sheet · link "All N sessions"
```

Example of a verdict history, as the sheet shows it (illustrative):

```
 Tue 14:00  SPOOFED   ip_list  "not in snapshot 2026-10-15"
 Mon 09:12  VERIFIED  ip_list  "in snapshot 2026-10-10"
```

## Screen 4: Activity (`/events`, `/sessions`)

Question: "What exactly happened?" Two tabs, **Events** and **Sessions**. The tab links keep the shared filters and show the totals. Page size is 50 with Previous and Next buttons. A new filter set starts at the first page.

### Events tab

Columns: Request (path, subline `method · source · session (8 chars) | no session`) · Status (code and word) · Traffic class · Agent (claimed name link + verdict pill, or "No agent name") · Confidence · Time.

Controls: search (`q`, searches the path), Agent select, HTTP status select, Source select. Counter: "N matching events".

| URL parameter | Meaning |
|---|---|
| `q` | Path contains (also `path`). |
| `agent` | Agent ID. |
| `status` | `200`, `403`, `429`, `403,429`, `4xx`, `5xx`, `4xx,5xx`. The short words `denied` and `errors` are also accepted and map to `403,429` and `4xx,5xx`. |
| `source` | `paired`, `cdn`, `origin`. |
| `verdict`, `verdict_id` | Verification result, or one verdict row (from the agent sheet). |
| `confidence` | `high`, `medium`, `low`. |
| `client_key`, `session`, `import_file` | Client key, session ID, import run. |
| `class`, `site`, `range` | Global filters. |
| `rec` | Show the evidence of a recommendation (see below). |

A filter without its own control (`path`, `session`, `confidence`, `verdict`, `verdict_id`, `client_key`, `import_file`) shows as a removable chip. A filter that the other tab cannot use shows the note "Not applied on this tab: ...". `[R4]`

### Event sheet (`event:<id>`)

```
 Header      method · path · status pill · time UTC
 Request     Observed: host · response time · bytes · referrer · client IP · client key · user agent
 Source      Observed: record type (CDN / Origin / Paired + pair state) · CDN / origin status ("not seen" if missing) ·
             import run (link -> Import sheet) · CDN bypass · request ID · file and line number
 Identity and classification   Inferred:
             identity ("Claims to be X, unverified" unless VERIFIED) · verdict · method · class · confidence ·
             rule and version · evidence · class evidence · inputs (verdict, category, UA type, edge signal) ·
             registry / IP list versions · checked time · verdict row #N (link -> Agent sheet)
             none: "No verdict for this request yet."
 Session     session ID (link -> Session sheet) · "Request k of n" · Previous / Next request buttons
 Recommendations   recommendations that use this event as evidence -> Recommendation sheet
 Note        status is observed; it does not prove that the task was completed
```

### Sessions tab

Columns: Session (8 chars; subline `agent · N pages · retry · loop · conversion`) · State (In progress / Closed) · Requests (link to Events with `session=`) · Traffic class · Confidence · Started.

Controls: Agent select, Session state select, chips "Has retry", "Has loop", "Reached conversion page".

| URL parameter | Meaning |
|---|---|
| `agent`, `state` (`closed`, `in_progress`) | Agent ID, state. |
| `retry`, `loop`, `conversion` | Chip on when set (any value). |
| `journey`, `reached` | Sessions of a journey that reached step N (from the Journeys tab). |
| `confidence`, `client_key` | As above (chips). |

### Session sheet (`session:<id>`)

```
 Header      agent link (-> Agent sheet) · class · state pill
 Summary     Observed: requests (link) · distinct pages · key pages visited · started · last seen · state ·
             confidence + reason · status counts · retry / loop signals · conversion page · journey steps reached
 Grouping    Inferred: "These N requests likely form one visit (gap < 30 min, same client)"
 Steps       Observed: ordered list: # · path · time · "+N s" from previous · flags (retry, loop, key page,
             conversion page) · status -> Event sheet
 Outcome     Unknown: "Task outcome unknown. Request logs show pages reached and response codes.
             They cannot show whether the task was completed."
 Gaps        list from activity reconstruction (for example "no CDN log: edge blocks unknown",
             "shared IP: may contain more than one agent"). Gaps that repeat the outcome text are hidden.
 Recommendations   that use this session as evidence -> Recommendation sheet
```

The grouping text and the gaps come from the API ([../activity-reconstruction/README.md](../activity-reconstruction/README.md)).

### Evidence of a recommendation (`rec=<id>`)

The list API cannot filter by recommendation. The screen shows a panel instead of the table: "Evidence for <target>", counts, a link "Back to recommendation", a remove button, and the evidence IDs (sessions on the Sessions tab, requests on the Events tab), each opening its sheet.

### Empty state

"No records match <active filters>." + "Clear filters".

## Screen 5: Pages & journeys (`/pages`, `/journeys`)

Question: "Where do agents go, and where do problems show?" Two tabs, **Pages** and **Journeys**.

### Pages tab

Toolbar: search (`q`, path, filtered in the browser), preset buttons (`preset`), counter. With a class filter set, the toolbar says "Page totals include all classes".

Preset views (each sends `view=` to the API):

| Preset (`preset`) | Label | Meaning |
|---|---|---|
| (empty) | All pages | |
| `agent_heavy` | Agent-heavy | Sorted by agent requests |
| `errors` | Errors | Error rate above 0 |
| `blocks` | Blocks | 403/429 above 0 |
| `retries` | Retries | Retries above 0 |
| `never_reached` | Key pages never reached | Key or sitemap key-content pages with 0 agent requests |

Columns: Page (path, tags key / conversion) · Status word (Not reached, Blocked, Errors, Retries, Healthy) · Agent requests · Error rate · Block rate (403/429) · Sessions · Agents · Retries · Median bytes. Rates are links to Events. A null rate shows a dash with the title "Unknown: no requests in this window". Sort: agent requests, then path.
A hint links to the Journeys tab. Empty: "No pages match this view" (the text depends on the preset).

### Page sheet (`page:<path>`)

```
 Chips         tags · In sitemap / Not in sitemap · access policy ("Allowed by policy" / "Blocked by intent")
 Page traffic  Observed: agent requests (link) · all requests · sessions
 Response by traffic class   Observed: per class: requests · 2xx · 3xx · 403 · 429 · other 4xx · 5xx (links to Events)
 Page signals  Observed: error rate · block rate · retries · median response size · agents
 Over time     Observed: requests and errors per hour
 Agents        claimed agent · class · sessions
 Sessions on this page     -> Session sheet
 Related recommendations   open recommendations on this page -> Recommendation sheet
 Foot          link "Inspect requests for this page" · Unknown: page content and task completion cannot be measured
```

Side-by-side classes show, for example, an AI crawler with 403 against a browser with 200.

### Journeys tab

One panel for each journey in the site config (`apps/api/config/sites`). Header: journey ID, "Critical" or "Standard", link "View evidence" (Journey sheet).

```
 Journey: apply-card  (Critical)                                              [Observed]
 1 /cards          ████████████  40   Entry                  None stopped here
 2 /cards/apply    █████         12   −28 · 70%              N stopped here · retries
 3 /cards/apply/done                   0   −12 · 100%        ended here
 By class table:  Class · Sessions · Step 2 · Step 3 ...  (numbers link to Sessions)
 Retries or loops by step: step 2: 5          Task outcome [Unknown]
```

A step number links to Sessions with `journey=<id>&reached=<step>` (and `class=<n>` in the class table). Step bar tone: pass; warn when a step keeps less than 50 % of the step before; fail when a step drops to 0. Footer hint: "Reached means a session requested the page. It does not show task completion." `[R6]`
Empty: "No journeys configured. Define journeys in the site config to see how far agents reach."

### Journey sheet (`journey:<id>`)

Chips (Critical or Standard) · Journey steps (bars with totals) · Reached by traffic class · Stopped at step · Retries / loops by step · Session grouping "Same client + time gap · inferred" · foot with the Unknown outcome text from the API.

## Screen 6: Data & pipeline (`/data`)

Question: "Is the data arriving, and is the pipeline working?" Main user: engineer.

Top strip (all tabs): one cell for each lane of the site (Fast, Slow): age of the last complete run, state (Healthy = healthy and run within 60 min; "No recent run" = healthy but older; "Late" = the API says unhealthy), plus an "Open alerts" cell (links to the Health & alerts tab when alerts exist).
Tabs (`tab`): `sources` (default), `imports`, `runs`, `health`.
Lanes and alerts come from `GET /health` and are filtered to the selected site.

### Sources tab

Toolbar: "N import files received", source select (used only for files whose name has no source), button **Upload log files**. The whole tab is a drop zone.

Table "Data sources": one row for each site and source (built from the newest 200 import files and the configured sources).

| Column | Content |
|---|---|
| Site / source | Site name and "CDN log" or "Origin log". A row opens the Import runs tab. |
| Status | Receiving, Stale (open alert for that source), Failed (last file failed), No files. |
| Files | Number of import files. |
| Note | Alert sentence (for example "No new logs from CDN for 75 min") or "Last import failed". |
| Last file | Time the last file was received. |
| Last event | Latest event time in the files. |

Below the table:
- "Source coverage": paired share (`paired_share_pct`) as "Origin requests paired with a CDN request", or Gap "Pairing is not measured: no paired source present."; one row for each configured source ("Present in the window" / "Not in the window"); link "Paired requests" to Events with `source=Paired`.
- "Current data gaps": `cannot_see` ("Cannot see") and `partial` ("Partial") texts from the overview, or "No data gaps reported."

Upload rules:
- Site and source come from the file name `<site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log[.gz]` (`src/lib/log-name.ts`, same rule as `apps/api/src/services/importer/log_names.py` and `samples/logs/README.md`). A file without that name uses the selected site and the source select.
- Files go in order of the start time in the name, one request each (`POST imports/upload?site=&source=`, body = file).
- One result row for each file: "Accepted. Queued until the import runs." (202), "Already stored. Not added again." (200, duplicate), or "Failed" + the API message. A file with no site fails with "No site. Select a site, or name the file <site>__<source>__<start>.log."
- The import lists reload when all files are sent.
- Import behaviour (inbox, dedup by sha256, overlap warning): [../ingestion/README.md](../ingestion/README.md).

### Import runs tab

Status filter (local to the page, not in the URL): All, Complete, Running, Failed. Up to 50 rows from the API. Footer: "Showing N import runs · TOTAL in this window".

Columns: File (8-char ID, site, source) · Status (Complete, Importing, Queued, Failed) · Imported ("of" total lines) · Note ("N rejected", or "Overlaps an earlier file") · Received. A row opens the Import sheet.

### Import sheet (`import:<id>`)

```
 Head         status pill · source · site · entry · priority
 Figures      Imported (of total lines) · Rejected (line numbers are not in the API) · Duplicates (skipped)
 Error        (failed files) "File could not be imported" + API error text
 Overlap      "Time range overlaps file X: possible double count"  (from overlap_warning)
 Import file  file ID · received · import finished · size · event time range · cleanup date
              (failed file: "Kept until a complete import")
 Note         "Raw rejected text is not stored. To add a file, use Upload log files on the Sources tab."
 Action       [Delete import] -> confirm step -> DELETE imports/{id}
```

Delete confirm text: the delete removes the events of the file and the file record. Sessions, pages and agents of the site are built again on the next pipeline run. A paired file of the other source is read again, so its own lines stay. The user can upload the same file again later.
While a file is importing, the button is replaced by a note. A 409 from the API (a run or import is active, or a paired file cannot be read) shows as "Delete failed" with the API text. After a delete, the sheet shows "Import deleted", the count of removed events, and the number of paired files read again. The import lists reload.

### Pipeline runs tab

Status filter (local): All, Complete, Running, Failed. Columns: Run (8-char ID, lane, site) · Status · Duration · Failed step · Started. A row opens the Run sheet.

### Run sheet (`run:<id>`)

```
 Head      status · lane · site
 Figures   Duration · Steps recorded
 Error     (failed) "Stopped at <step>" + error text
 Steps     one entry for each step in the run counts: name · non-zero counters (or "All counters 0") ·
           "Complete" or "Failed" for the failed step
 Summary   run ID · started · finished
 Note      "Time for each step is not in the API."
```

### Health & alerts tab

- "Alerts": open alerts: sentence ("No new logs from CDN for 75 min"), raw kind, last file time, site, raised time. "No open alerts" when empty. Cleared alerts are not shown.
- "Lanes": lane · Healthy or Late · last complete run time ("No complete run yet").

## Key user tasks

### Task A: PM acts on a recommendation

```
 PM            Overview        Recommendation sheet      Session sheet        Event sheet
 │ open app      │                      │                      │                   │
 │──────────────►│ top 3 recs           │                      │                   │
 │ click #1      │─────────────────────►│ priority + factors, labels, fact bundle  │
 │ click a session ID                   │─────────────────────►│ steps, gaps,      │
 │               │                      │                      │ outcome Unknown   │
 │ click a 403 step                                            │──────────────────►│ verdict + rule
 │ decides: send the journey to Agentrek (outside the system)                      │
```

### Task B: "Is this really GPTBot?"

```
 Agents -> GPTBot -> sheet "Why this class" (rule, inputs, versions)
                  -> "Verdict history" (VERIFIED Mon, SPOOFED Tue: new IP-list snapshot)
                  -> "Inspect requests with this verdict" -> Events (verdict_id)
```

### Task C: Data looks old

```
 Chip "Last run failed"   -> Data & pipeline, Health & alerts -> Pipeline runs -> Run sheet (step, error)
 Chip "No recent data"    -> Health & alerts -> alert for the source -> Sources: last file time -> check the log delivery
```

### Task D: Number drill-down (any number)

```
 Overview "Denial rate 4.2 %" -> Events: site, range, status 403,429
                              -> Event sheet -> Session sheet
```

### Task E: Generate recommendations now

```
 Recommendations -> [Generate now] -> "Running…" -> new run shown
                 -> lock taken: message "Another run is active", button usable again after the answer
```

## Label map (where each label shows)

```
 Observed   counts · status codes · times · paths · page order · verdict method result ·
            "reached step N" · edge and origin status
 Inferred   session grouping · confidence · class 4 and 5 from the edge signal ·
            "Potential issue" · priority factors · "maybe soft failure" (bytes far below median, pattern P4)
 Unknown    task outcome · content understood · edge blocks with no CDN log ·
            undeclared bots (class 6) · uncertainty part of "Suggested next step"
```

## States (every screen)

| State | Behaviour |
|---|---|
| Loading | A skeleton of the screen (`LoadingState`). On a reload the old data stays visible `[D7]`. |
| Empty | Say why (no data in range, no run yet, filter too narrow) and give one next step. |
| Stale | Freshness chip, rail foot and status row `[R5]`. |
| Error | `ErrorState`: title, API message, API `code`, `HTTP <status>`, and a "Try again" button. Never a blank screen. Network failure: "The dashboard server did not answer. Check the connection and retry." Proxy failure: `api_unreachable`. |
| In-progress session | Pill "In progress". |
| LLM fallback | The recommendation sheet footer shows the text source note ("Template text ..."). The list footer shows "Model none (template text)". |
| Missing source | Gap text where the answer would be `[R4]`: "Unknown", "No data", "No text stored.", "Pairing is not measured: ...". |
