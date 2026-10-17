# Dashboard — UI / UX Flows (Flow 6)

Source for the mock dashboard. Content, structure, and behaviour only. No visual design (colours, fonts, styling) in this file.

Based on: `mvp-flows.md` (Flows 1–7, locked), `task.pdf` §02, §03.D, §04, §05, §09.

---

## 1. Users

| User | Goal | Main screens |
|---|---|---|
| Webzero PM (primary) | Decide which journeys to test next. Trust the reason. | Recommendations, Overview, Pages & Journeys |
| Engineer | Check that data arrives and the pipeline works. Debug a verdict. | Data & Pipeline, Activity Explorer |
| AI agent / script | Read the same data without the UI (Webzero is agent-first). | JSON API with the same filters and IDs as each screen (§9) |

---

## 2. UX rules (apply to every screen)

| # | Rule | From |
|---|---|---|
| R1 | Every statement has a label: **Observed**, **Inferred** or **Unknown**. A legend is always reachable. | PDF §02 (outranks every feature) |
| R2 | Every number is a link. Click → Activity Explorer (or Sessions) with the filters that produced the number. | PDF §03.D "every metric drills down" |
| R3 | A claimed identity is shown as "claims to be X, unverified" until the verdict is VERIFIED. | PDF §02 trap 3 |
| R4 | Show the gaps. When the data cannot answer, say so in the place where the answer would be (e.g. "Edge blocks: Unknown — no CDN log for this site"). | PDF §03.C |
| R5 | Freshness is always visible (banner). Stale or failed data is never shown as current. | Flow 7 |
| R6 | A 200 is not success. Never show "success" for a journey. Show "reached step N"; outcome = Unknown. | PDF §02 trap 2 |
| R7 | Every class, verdict, confidence and priority can be explained in one click ("why?" → rule, inputs, versions). | PDF §05 auditability |
| R8 | Global filters (site, time range, class) stay the same when the user moves between screens, and are in the URL. | Navigation, shareable links, agent access |

---

## 3. Navigation map

```
 ┌───────────────────────────────────────────────────────────────────────┐
 │ GLOBAL BAR: site · time range · class filter · freshness banner ·     │
 │             label legend                                             │
 └───────────────────────────────────────────────────────────────────────┘
        │
        ├── 1 Overview ─────────────┐ (landing page)
        ├── 2 Recommendations ──────┼──► Recommendation detail ──► Sessions / Events
        ├── 3 Agents ───────────────┼──► Agent detail ──────────► Sessions / Events
        ├── 4 Activity Explorer ────┼──► Event detail ──► Session detail
        │      (Events | Sessions)  │
        ├── 5 Pages & Journeys ─────┼──► Page detail / Journey detail ──► Sessions
        └── 6 Data & Pipeline ──────┘──► Import run detail · Pipeline run detail
            (Settings: read-only view of config, inside 6)
```

All roads end at the same two evidence screens: **Session detail** and **Event detail**.

---

## 4. Global elements

### 4.1 Global bar

| Element | Behaviour |
|---|---|
| Site selector | One site at a time. Changing it resets the screen data, keeps the time range. |
| Time range | Presets: last 1 h, 6 h, 24 h, 7 d, custom. Default: last 24 h. |
| Class filter | Multi-select of the 6 classes. Default: all. |
| Freshness banner | From `pipeline_runs` (Flow 7). See 4.2. |
| Label legend | Short definitions of Observed / Inferred / Unknown. |
| "Generate recommendations now" | Visible on Recommendations only (§6.2). |

### 4.2 Freshness banner states

```
 State                         Text
 ───────────────────────────── ─────────────────────────────────────────────────────
 OK                            "Data up to 14:05"
 Last fast run failed          "Data up to 13:55 · last run failed at Verify" → link to run
 3 failures in a row           "ALERT: pipeline failing since 13:40" → link to run
 No new data for a site > 1 h  "ALERT: no new logs from bank.com since 12:58" → Data & Pipeline
 Run in progress               "Updating… (data up to 14:00)"
```

### 4.3 The 6 classes (names used everywhere)

```
 1 Verified search crawler      4 Browser automation / agent-like
 2 Known AI crawler             5 Ordinary browser
 3 Other identifiable bot       6 Unknown
```

### 4.4 Verdict and confidence (names used everywhere)

```
 Verdict:     VERIFIED · CLAIMED · UNVERIFIED · SPOOFED · UNKNOWN
 Confidence:  High · Medium · Low
```

---

## 5. Screen 1 — Overview (landing page)

Question it answers: "What is happening on this site, and what needs attention?"

### Content (top to bottom)

```
 [Top recommendations]   3 highest-priority open items from the latest run
                         each: rank · target · pattern · priority · confidence · status
                         link → Recommendations

 [Key numbers]           Total requests · AI or automated share · Distinct agents ·
                         Error rate · Denial rate (403/429)
                         each: value · change vs previous period · label: Observed

 [Traffic by class]      6 classes × confidence (High / Medium / Low) · counts + share

 [Trend]                 requests over time, one series for each class

 [Top pages]             top 10 paths by agent requests (classes 1–4) · errors · blocks

 [Coverage]              what this data can and cannot show (see below)
```

### Coverage panel (honest limits, always on Overview)

```
 Sources for this site:   CDN log ✓ · origin log ✓ · paired ✓ (98 % of origin events)
 Unknown share:           31 % of requests are class 6
 Cannot see:              task completion · page content · clicks / form steps
 Partial:                 browser traffic without edge bot signal = Unknown
```

### Interactions

| Click | Goes to |
|---|---|
| Any key number | Activity Explorer → Events, with the filter behind the number |
| A class × confidence cell | Activity Explorer → Events, filtered to that class + confidence |
| A trend point | Activity Explorer → Events for that time bucket + class |
| A top page | Page detail |
| A top recommendation | Recommendation detail |
| "Unknown share" | Activity Explorer filtered to class 6, grouped by reason |

### Empty state

"No data for this site in this time range." + last import time + link to Data & Pipeline.

---

## 6. Screen 2 — Recommendations (the centrepiece)

Question: "Which journeys should Webzero test next, and why?"

### 6.1 Run header

```
 Run #14 · window 08:00–14:00 (6 h) · created 14:02 · rule v3 · prompt v2 · model <name>
 Compared with run #13:  2 new · 3 still open · 1 gone
 [Generate recommendations now]   [Run history ▾]
```

### 6.2 "Generate now" button

```
 Click ──► run-pipeline slow
   ├─ lock free  ──► button shows "Running…" ──► list reloads with the new run
   ├─ lock taken ──► "A pipeline run is active. Try again in a few minutes."
   └─ run fails  ──► "Run failed at <step>. Previous list is still shown." → link
```

The previous list stays visible while a new run is active.

### 6.3 List

| Column | Content |
|---|---|
| Rank | 1, 2, 3 … by priority |
| Status | New · Still open · (Gone items in a separate section) |
| Recommended test | Page, task or journey to test |
| Pattern | Product discovery · Blocked access · Broken navigation · Content discoverability · Full-journey simulation |
| Priority | Score + factors (e.g. `18 = 3 × 2 × 3 × 1.0`) |
| Confidence | High / Medium / Low |
| Evidence | "12 sessions · 40 events" (link) |

Filters: pattern, status, confidence. Sort: priority (default).

### 6.4 Recommendation detail (8 PDF fields)

```
 Recommended test       Agent journey /products → /pricing → /apply
 Reason                 <text>                                         [Observed]
 Evidence               12 sessions · 40 events → list (links)         [Observed]
 Potential issue        <text>                                         [Inferred]
 Suggested validation   <text>
 Priority               18 = Impact 3 × Frequency 2 × Severity 3 × Confidence 1.0
                        each factor: value + why (e.g. "Impact 3: /pricing is a key page")
 Confidence             High — "verified identity, IP not shared"
 Next action            <text, includes the Unknown part + why simulation> [Unknown]

 Text source:  "Written by LLM (model, prompt v2), checked against facts"  or
               "Template text (LLM unavailable / failed check)"
 Fact bundle:  expandable list of the exact facts given to the LLM
 History:      first seen in run #11 · in runs #11–#14
 Related:      other recommendations on the same journey
```

### 6.5 Run history

List of runs: run ID · window · created · counts (new / open / gone) · rule version. Click → view that run's list as it was (append-only, Flow 5).

### Empty states

- No run yet: "No recommendations yet. Runs every 6 h, or generate now."
- Run with 0 candidates: "No pattern met its threshold in this window." + thresholds used + link to Settings.

---

## 7. Screen 3 — Agents (Agent directory, V2)

Question: "Who is visiting?"

### List

| Column | Content |
|---|---|
| Agent | Claimed name (registry). No bot name → "Unknown (browser UA)" etc. for each class |
| Class | 1–6 |
| Verification | VERIFIED / CLAIMED / UNVERIFIED / SPOOFED / UNKNOWN, with R3 wording |
| First seen · Last seen | Times |
| Requests · Sessions · Distinct pages | Numbers (links) |
| Common paths | Top 3 |

Filters: class, verification. Search: agent name.

### Agent detail

```
 Header:          name · vendor · class · current verdict · confidence
 Why this class:  rule ID · inputs (verdict, category, UA type, edge signal) · rule v · registry v
 Verdict history: append-only rows (Flow 2), newest first
                  e.g. Tue 14:00  SPOOFED   ip_list  "not in snapshot 2026-10-15"
                       Mon 09:12  VERIFIED  ip_list  "in snapshot 2026-10-10"
                  each row → events that point to it
 Client keys:     list of (UA, IP) pairs for this agent · shared-IP flag
 Activity:        requests over time · top paths · status mix
 Sessions:        list → Session detail
```

---

## 8. Screen 4 — Activity Explorer

Question: "What exactly happened?" Two tabs: **Events** and **Sessions**.

### 8.1 Events tab

Table columns: time · method · path · status · class · agent (claimed) · verdict · confidence · source (CDN / origin / paired) · session.

Filters (all in the URL): time, class, agent, verdict, confidence, status (exact or 2xx/3xx/4xx/5xx), path (contains), client key, session ID, source, import run.

Search: path, UA text.

Timeline: count of events over time for the current filter.

### 8.2 Event detail (drawer or page)

```
 Request (Observed)   time · host · method · path + query · status · bytes · response time ·
                      referrer · UA · client IP
 Source               CDN line / origin line / paired (edge status + origin status) ·
                      import run · file · line number
 Verdict (Flow 2)     claimed identity · verdict · method · evidence text · registry v ·
                      checked_at · "verdict row #N" (link to agent verdict history)
 Class (Flow 3)       class · confidence · rule ID · rule v · inputs used
 Session              session ID (link) · position in session (step k of n)
 Recommendations      recommendations that use this event as evidence
```

### 8.3 Sessions tab

Table columns: session ID · client (agent / UA) · class · confidence · started · last seen · state (in progress / closed) · requests · distinct pages · retry · loop · reached conversion.

Filters: class, confidence, state, has retry, has loop, reached conversion, agent, journey.

### 8.4 Session detail

```
 Header      agent · class · confidence + reason · started · last seen ·
             state: "In progress (last event 8 min ago, can still grow)" / "Closed"
 Summary     requests · distinct pages · status counts · retry ✓/✗ · loop ✓/✗ ·
             journey steps reached                                     [Observed]
 Grouping    "These N requests likely form one visit (gap < 30 min, same client)"
                                                                       [Inferred]
 Steps       ordered list: time · path · status · Δ time from previous · flags
             (retry / loop / key page / conversion page) · link to event
 Outcome     "Task outcome: Unknown — logs cannot show completion"     [Unknown]
 Gaps        list from Flow 4 (e.g. "no CDN log: edge blocks unknown",
             "shared IP: may contain more than one agent")
```

---

## 9. Screen 5 — Pages & Journeys (V3)

Question: "Where do agents go, and where do problems show?" Two tabs: **Pages** and **Journeys**.

### 9.1 Pages tab

Table: path · tags (key / conversion) · agent requests · sessions · distinct agents · error rate · block rate (403/429) · retries · median bytes.

Preset views (each = a saved filter):

```
 Agent-heavy pages        sort by agent requests
 Pages with errors        error rate > 0
 Pages with blocks        403/429 > 0
 Pages with retries       retries > 0
 Key pages never reached  key / sitemap key-content pages with 0 agent requests
```

### 9.2 Page detail

```
 Header            path · tags · in sitemap ✓/✗ · access policy (allowed / blocked by intent)
 By class          requests and status mix for each class (side by side, e.g. AI 403 vs browser 200)
 Over time         requests and errors over time
 Agents            which agents fetched it
 Sessions          sessions that include this page
 Recommendations   open recommendations on this page
```

### 9.3 Journeys tab

One block for each journey in `site_config`:

```
 Journey: apply-card  (critical)
 Steps:   /cards → /cards/apply → /cards/apply/done

 Class 2 (Known AI crawler)    40 sessions → 12 reached step 2 → 0 reached step 3   [Observed]
 Class 4 (Automation)           8 sessions →  3 reached step 2 → 0 reached step 3   [Observed]
 Retry / loop at step:         step 2: 5 sessions                                   [Observed]
 Outcome:                      Unknown — logs cannot show task completion            [Unknown]
```

Click a step count → the sessions that reached (or stopped at) that step.

---

## 10. Screen 6 — Data & Pipeline

Question: "Is the data arriving, and is the pipeline working?" Main user: engineer.

### 10.1 Sources (for each site)

```
 Site       Source        Format / field map   Last file    Last event   Paired   Status
 bank.com   CDN log       <vendor>.yaml        14:01        13:59        98 %     OK
 bank.com   origin log    nginx combined       14:00        13:59        —        OK
 shop.com   origin log    nginx combined       12:58        12:57        —        ALERT: no data > 1 h
```

### 10.2 Import runs

Table: file · site · source · received · status (new / importing / success / failed) · lines · imported · rejected · duplicates skipped · will be deleted on (cleanup date).

Import run detail:

```
 Counts        lines · imported · rejected · duplicates
 Rejects       line number · reason   (line text is NOT shown — not stored, Flow 1)
 Overlap       "Time range overlaps file X: possible double count" (nginx, no request ID)
 Actions       [Force import again]  (bypasses the sha256 check, Flow 1 decision 1.9)
```

Upload: [Upload log file] → choose site + source → file goes to the inbox → shows as "new".

### 10.3 Pipeline runs

Table: run ID · lane (fast / slow) · started · finished · status · failed step · counts per step.

Run detail: each step with status, duration, items processed, error text (if failed).

### 10.4 Health and alerts

```
 Fast lane   last success 14:05 · healthy
 Slow lane   last success 14:02 · healthy
 Alerts      list: time · type (no data / 3 failures) · site · cleared at
```

### 10.5 Settings (read-only in MVP)

Shows the current config files, with version:

```
 site_config     key pages · conversion pages · journeys (critical ✓/✗)
 access policy   robots.txt snapshot · allow / block list
 sitemap         URLs · key-content URLs
 thresholds      pattern thresholds · frequency buckets · window (6 h)
 registry        version · number of bots · IP-list snapshot dates
 field maps      one for each CDN
```

Editing = change the files (no UI editor in MVP).

---

## 11. Key user flows

### F-A: PM acts on a recommendation

```
 PM            Overview        Recommendations     Rec detail        Session detail    Event detail
 │ open app      │                   │                  │                   │                 │
 │──────────────►│ top 3 recs        │                  │                   │                 │
 │ click #1      │──────────────────────────────────────►│                   │                 │
 │               │                   │   8 fields, priority factors,         │                 │
 │               │                   │   labels, fact bundle                 │                 │
 │ click "12 sessions"                                   │──────────────────►│                 │
 │               │                   │                  │   steps, gaps,    │                 │
 │               │                   │                  │   outcome Unknown │                 │
 │ click a 403 step                                                          │────────────────►│
 │               │                   │                  │                   │  verdict + rule │
 │ decides: send journey to Agentrek (outside the system)                                      │
```

### F-B: "Is this really GPTBot?"

```
 Agents → GPTBot → "Why this class" (rule, inputs, versions)
                 → Verdict history (VERIFIED Mon, SPOOFED Tue: new IP-list snapshot)
                 → click a verdict row → events that used that verdict
```

### F-C: Data looks old

```
 Banner "last run failed at Verify" → Pipeline run detail (step, error)
 Banner "no data from shop.com > 1 h" → Sources → last file 12:58 → check the log delivery
```

### F-D: Number drill-down (any number)

```
 Overview "Denial rate 4.2 %" → Activity Explorer
     filter: site, time range, status ∈ {403, 429}
     → Event detail → Session detail
```

### F-E: Generate recommendations now

```
 Recommendations → [Generate now] → "Running…" → new run #15 shown
                                   → lock taken: message, button disabled until free
```

---

## 12. Label map (where each label shows)

```
 Observed   counts · status codes · times · paths · page order · verdict method result ·
            "reached step N" · edge/origin status
 Inferred   session grouping · confidence · class 4/5 from edge signal ·
            "Potential issue" · P4 "maybe soft failure" (bytes far below median)
 Unknown    task outcome · content understood · edge blocks with no CDN log ·
            undeclared bots (class 6) · "Next action" uncertainty part
```

---

## 13. States (every screen)

| State | Behaviour |
|---|---|
| Loading | Keep the old data visible with "Updating…" when possible. |
| Empty | Say why (no data in range / no run yet / filter too narrow) + one next step. |
| Stale | Freshness banner (4.2). |
| Error | Say what failed + link to the run. Never a blank screen. |
| In-progress session | Label "In progress", with last event age. |
| LLM fallback | "Template text" marker on the recommendation. |
| Missing source | Gap text where the answer would be (R4). |

---

## 14. URLs and agent access

Every screen has a stable URL. Filters are query parameters. The same path under `/api` returns JSON with the same data, IDs and labels.

```
 UI                                      API (JSON)
 /overview?site=&from=&to=&class=        /api/overview?…
 /recommendations?run=                   /api/recommendations?run=
 /recommendations/{rec_id}               /api/recommendations/{rec_id}
 /agents · /agents/{agent_id}            /api/agents · /api/agents/{agent_id}
 /events?…filters                        /api/events?…filters   (paged)
 /events/{event_id}                      /api/events/{event_id}
 /sessions?… · /sessions/{session_id}    /api/sessions?… · /api/sessions/{session_id}
 /pages · /pages?path=                   /api/pages · /api/pages?path=
 /journeys · /journeys/{journey_id}      /api/journeys · /api/journeys/{journey_id}
 /data/imports · /data/runs · /data/health   /api/imports · /api/runs · /health
 POST /api/recommendations/generate      (same as the button; 409 if the lock is taken)
```

Rules for the API:

- Each value carries its label (`"label": "observed" | "inferred" | "unknown"`).
- IDs are the same as in the UI (rec IDs, session IDs, event IDs), so a link from a human and a call from an agent reach the same record.
- Lists are paged, with a stable sort.

---

## 15. Out of scope (MVP)

- Login and access control (known gap, internal system; PDF §05 requires it before customer use).
- Editing config in the UI (files only).
- Live streaming / push updates (near real-time through the 5-min runs is enough, Flow 7).
- Export, alerts by email/Slack, multi-site comparison.
- Visual design.

## 16. Open questions

- Default time range: 24 h or the recommendation window (6 h)?
- Do "Gone" recommendations show by default or only in run history?
