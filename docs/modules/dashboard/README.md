# Dashboard

The dashboard is the Next.js web console (`apps/dashboard`). It shows agent traffic, the evidence behind each number, and the journeys to test next.
Input: JSON from the FastAPI back end, through the same-origin proxy `/dashboard-api`. Output: six screens, detail sheets, and three actions (upload log files, delete an import, generate recommendations).

Per-screen content is in [screens.md](screens.md). Do not copy it here.

## Read this when

- You add or change a screen, a table column, a filter, a detail sheet, or a link between screens.
- You change what the UI shows for freshness, labels (Observed, Inferred, Unknown), gaps, or empty and error states.
- You change the proxy `src/app/dashboard-api/[...path]/route.ts` or `API_URL` / `API_TOKEN`.
- You add an API call, or the API changes a response shape (update `src/lib/api/types.ts`).
- You change a URL, a URL query parameter, or the global filters (site, range, class).
- You check that a UI rule (R1 to R8) still holds after a change.
- You need the traffic class names. They are in [../classification/README.md](../classification/README.md).

## Code map

All paths are under `apps/dashboard/` unless they start with `docs/` or `deploy/`.

| Path | Purpose |
|---|---|
| `package.json` | Scripts (`dev`, `build`, `start`, `lint`, `test`) and dependencies (Next.js 16.4.2, React 19.3.0, Base UI, shadcn, Lucide). |
| `next.config.ts` | Next.js config: `cacheComponents`, `partialPrefetching`, Tailwind loader for `*.css`. |
| `AGENTS.md` | Rule for AI agents: read `node_modules/next/dist/docs/` before you write Next.js code. This Next.js version has breaking changes. |
| `.env.example` | `API_URL` and `API_TOKEN` (server side only). |
| `src/app/layout.tsx` | Root layout: fonts (Instrument Sans, JetBrains Mono), tooltip provider, page metadata. |
| `src/app/[[...view]]/page.tsx` | One catch-all page. It renders `<Dashboard />` for every UI URL. |
| `src/app/dashboard-api/[...path]/route.ts` | Same-origin proxy to the API. Adds the Bearer token. |
| `src/app/globals.css`, `src/app/styles/*.css` | Styles. `globals.css` only imports `styles/`. See "Styles" below. |
| `src/lib/api/client.ts` | `apiGet`, `apiPost`, `apiDelete`, `apiHealth`, `queryString`, `ApiError`. |
| `src/lib/api/use-api.ts` | `useApi`, `useScopedApi`, `useQuery`, `invalidate`. |
| `src/lib/api/filters.ts` | Global filters: `ranges`, `defaultRange`, `scopeFromQuery`, `scopeParams`. |
| `src/lib/api/types.ts` | TypeScript types for the API JSON (one per response model in `apps/api/src/models/api.py`). |
| `src/lib/classes.ts` | `classMeta`: class id, name, short name, chart colour. `classOf(id)`. |
| `src/lib/format.ts` | UTC date and number helpers (`dateTimeUTC`, `windowCaption`, `formatBytes`, ...). |
| `src/lib/log-name.ts` | `parseLogName`: reads site, source and start time from a log file name. |
| `src/lib/api/api.test.mjs`, `src/lib/log-name.test.mjs` | The only tests (`npm test`). |
| `src/components/dashboard/dashboard.tsx` | App frame: reads the URL, routes between screens, holds the detail-sheet state, fetches sites and the overview for freshness. |
| `src/components/dashboard/shared.tsx` | Shared parts: `Label`, `Gap`, `NumberLink`, `Panel`, `ApiGate`, `LoadingState`, `ErrorState`, `NoData`, `Empty`, `Select`, `Segmented`, `ClassFilter`, `SearchField`, `Confidence`, `Status`, `Tip`. |
| `src/components/dashboard/trend-chart.tsx` | Stacked bar chart of requests per class (Overview). |
| `src/components/dashboard/shell/` | `rail.tsx` (side nav), `topbar.tsx` (freshness chip, label guide), `filter-bar.tsx` (site, range, class), `detail-sheet.tsx` (sheet host), `nav-config.ts` (nav items, range buttons). |
| `src/components/dashboard/overview/` | Overview panels: `metrics`, `recommendations`, `classes`, `top-pages`, `coverage`. |
| `src/components/dashboard/sections/` | One folder or file per screen: `recommendations/`, `agents.tsx`, `activity/`, `pages-journeys/`, `data-pipeline/`. `common.ts` holds the shared `Props` type. |
| `src/components/dashboard/sections/data-pipeline/upload.tsx` | Multi-file upload and drop zone (Sources tab). |
| `src/components/dashboard/details/` | One detail sheet per entity (`recommendation`, `agent`, `event`, `session`, `page`, `journey`, `run`, `import`, `legend`). `index.tsx` maps the type to the sheet. |
| `src/components/ui/` | shadcn primitives: `badge`, `button`, `sheet`, `tooltip`. |
| `README.md` | Run and check commands, styles, file map (short form of this page). |
| `deploy/dashboard/Dockerfile` | Production image (build context `apps/dashboard`). See [../deployment/README.md](../deployment/README.md). |
| `deploy/compose/docker-compose.yml`, `deploy/helm/agent-analytics/templates/dashboard.yaml` | Set `API_URL` and `API_TOKEN` for the dashboard service. |

### Styles

- `src/app/styles/tokens.css`: design tokens and the Tailwind `@theme` mapping.
- `base.css`, `shell.css`, `controls.css`, `panels.css`, `table.css`, `chart.css`, `detail.css`: shared rules.
- `detail-*.css`: one file per detail sheet.
- `overview.css`, `recommendations.css`, `agents.css`, `activity.css`, `pages.css`, `data.css`: screen rules.
- `focus.css`: keyboard focus. It loads last.
- Class chart colours are in `src/lib/classes.ts`.

## Data flow

```
 Browser (React client)                Next.js server                 FastAPI (apps/api)
 ┌────────────────────────┐   GET/POST/DELETE      ┌───────────────────────────┐  +Bearer API_TOKEN   ┌──────────┐
 │ URL: path + ?site=     │  /dashboard-api/api/*  │ route.ts (proxy)          │ ───────────────────► │ /api/*   │
 │   &range=&class=       │ ─────────────────────► │  - allow /api/* + /health │   ${API_URL}/api/*   │ /health  │
 │   &detail=type:id      │  /dashboard-api/health │  - read API_URL, API_TOKEN│                      │          │
 │ scope -> useScopedApi  │ ◄───────────────────── │  - no-store               │ ◄─────────────────── │ JSON     │
 │ ApiGate -> screen      │   JSON (status kept)   │  - 502 api_unreachable    │   JSON (status kept) │          │
 └────────────────────────┘                        └───────────────────────────┘                      └──────────┘
   browser never sees API_URL or API_TOKEN
```

Data path inside the browser:

```
 URL query (site, range, class)
        │ scopeFromQuery()
        ▼
 Scope {site, range, classes} ──scopeParams()──► {site, from, to, class}   (from/to = now - range, set at fetch time)
        │
        ▼
 useScopedApi(path, scope, extra) ──apiGet──► /dashboard-api/api/<path>?...
        │  key = path|site|range|classes|extra   (new key aborts the old request)
        ▼
 ApiState {data, error, loading, reload} ──► ApiGate ──► skeleton | ErrorState | screen
        ▲
        └── invalidate("imports") reloads every mounted query whose key starts with "imports"
```

Sequence: generate recommendations now (Recommendations screen).

```
 User        Recommendations      dashboard-api proxy        FastAPI
  │ click        │                       │                       │
  │ Generate now │                       │                       │
  │─────────────►│ button = "Running…"   │                       │
  │              │ POST recommendations/generate?site=S          │
  │              │──────────────────────►│ POST /api/recommendations/generate?site=S
  │              │                       │──────────────────────►│ run slow lane now
  │              │                       │◄──────────────────────│ 200 {status, run}
  │              │◄──────────────────────│                       │   | 409 lock_taken
  │              │ notice + list.reload() + runs.reload()        │   | 500 run_failed
  │◄─────────────│ new run shown (old list stays until then)     │
```

Sequence: upload log files (Data & pipeline, Sources tab).

```
 User         upload.tsx                proxy                    FastAPI
  │ pick/drop    │                        │                        │
  │ N files      │ sort by start time in the file name            │
  │─────────────►│ for each file, one at a time:                  │
  │              │ POST imports/upload?site=&source= (body = file)│
  │              │───────────────────────►│───────────────────────►│ 202 accepted | 200 duplicate | 4xx
  │              │◄───────────────────────│◄───────────────────────│
  │◄─────────────│ one result row per file; imports.reload() at the end
```

## Rules and decisions

UX rules. They apply to every screen.

| ID | Rule | Why |
|---|---|---|
| `[R1]` | Every statement has a label: **Observed**, **Inferred** or **Unknown**. A legend is always reachable (top bar "Label guide"). | Trust in each claim comes before every feature. |
| `[R2]` | Every number is a link. Click opens Activity (Events or Sessions) with the filters that made the number. A zero has no link (`NumberLink`). | Every metric must drill down to evidence. |
| `[R3]` | A claimed identity shows as "claims to be X, unverified" until the verdict is VERIFIED. | A user agent string is a claim, not proof. |
| `[R4]` | Show the gaps. When the data cannot answer, say so where the answer would be (`Gap` component). | An empty cell looks like zero. A gap text tells the truth. |
| `[R5]` | Freshness is always visible. Stale or failed data is never shown as current. | Users must know how old the data is. |
| `[R6]` | A 200 is not success. Never show "success" for a journey. Show "reached step N". Outcome is Unknown. | Request logs cannot show task completion. |
| `[R7]` | Every class, verdict, confidence and priority explains itself in one click (rule, inputs, versions). | The system must be auditable. |
| `[R8]` | Global filters (site, time range, class) stay the same when the user changes screen, and they are in the URL. | Links are shareable. Scripts can use the same URL. |

Code rules.

| ID | Rule | Why |
|---|---|---|
| `[D1]` | No login in the UI. Access control is the API token on the dashboard server. | Internal system. A login is required before customer use (see Out of scope). |
| `[D2]` | The browser calls only `/dashboard-api/*`. The browser never gets `API_URL` or `API_TOKEN`. | The API has no CORS, and the token must stay on the server. |
| `[D3]` | The dashboard holds no business logic and no SQL. Counts, classes, verdicts, priorities, freshness text and gap text come from the API. The UI only formats them. | One source of truth. The JSON API serves agents and scripts with the same data. |
| `[D4]` | UI IDs equal API IDs (recommendation IDs, session IDs, event IDs, agent IDs, page paths). A link from a person and a call from a script reach the same record. | The product is agent-first. |
| `[D5]` | One URL for each screen. Filters are query parameters. A detail sheet is the `detail=<type>:<id>` parameter. | Shareable, bookmarkable, scriptable. |
| `[D6]` | All times show in UTC. | The API sends UTC. No local-time confusion between users. |
| `[D7]` | On reload, the old data stays on screen until the new answer arrives. An answer for an old key is never shown. | No flicker. No stale answer under new filters. |
| `[D8]` | The six traffic class names and colours are fixed in `src/lib/classes.ts`. Counts always come from the API. | Names must match [../classification/README.md](../classification/README.md). |
| `[D9]` | The dashboard does not edit configuration. Sites, bot registry, thresholds are files. | Config is data in `apps/api/config`. |
| `[D10]` | The previous recommendation list stays visible while a new run is active or after a run fails. | A failed run must not blank the list. |

## Configuration

Environment variables (read by the dashboard server at request time, not at build time):

| Setting | Default | Effect |
|---|---|---|
| `API_URL` | `http://localhost:8000` | Base URL of the FastAPI back end. Compose sets `http://api:8000`. Trailing `/` is removed. |
| `API_TOKEN` | empty (no header) | Bearer token sent to `/api/*`. Must match the API `API_TOKEN`. Leave empty only when the API is open (dev). |

Constants in code:

| Name (file) | Value | Effect |
|---|---|---|
| `defaultRange` (`src/lib/api/filters.ts`) | `24h` | Range when the URL has none or an unknown one. |
| `ranges` (`src/lib/api/filters.ts`) | `1h`, `6h`, `24h`, `7d` | Time range presets. `7d` uses day buckets. The others use hour buckets. |
| `PAGE_SIZE` (`sections/activity/config.ts`) | `50` | Rows per page in Events and Sessions. |
| `SESSION_ID_CHARS` (`sections/activity/config.ts`) | `8` | Characters of a session ID shown in tables. |
| `RUN_LIST_LIMIT` (`sections/data-pipeline/config.ts`) | `50` | Rows requested for the import and pipeline run lists. |
| `SOURCE_FILE_LIMIT` (`sections/data-pipeline/config.ts`) | `200` | Import files read to build the Sources table. |
| `LIVE_WINDOW_MINUTES` (`sections/data-pipeline/config.ts`) | `60` | A healthy lane older than this shows "No recent run". |
| `BLOCK_RATE_FAIL_PCT`, `ERROR_RATE_FAIL_PCT` (`sections/pages-journeys/config.ts`) | `10` | A rate at or above this value is a failure mark. A rate above 0 is a warning mark. |
| `JOURNEY_DROP_WARN_RATIO` (`sections/pages-journeys/config.ts`) | `0.5` | A journey step that keeps less than this share of the step before it is a warning. |
| `PAGE_PRESETS` (`sections/pages-journeys/config.ts`) | 6 values | Preset views of the Pages tab. |
| `TABS`, `STATUS_FILTERS` (`sections/data-pipeline/config.ts`) | see [screens.md](screens.md) | Tabs and status filters of Data & pipeline. |

Thresholds for recommendation patterns are API side. See [../recommendations/README.md](../recommendations/README.md).

## Interfaces

### Proxy `/dashboard-api/*` (`src/app/dashboard-api/[...path]/route.ts`)

| Item | Behaviour |
|---|---|
| Methods | `GET`, `POST`, `DELETE`. |
| Allowed paths | `/dashboard-api/api/<...>` (at least one segment after `api`) and `/dashboard-api/health`. Other paths answer `404 {"detail":{"code":"not_found",...}}`. A `.` or `..` segment is refused. |
| Forward | `${API_URL}/<path>?<same query>`. Header `Accept: application/json`. Header `Authorization: Bearer ${API_TOKEN}` only when the token is set. `POST` also forwards `Content-Type` and the body (streamed). |
| Response | Same status and `Content-Type` as the API. Header `Cache-Control: no-store`. Redirects are not followed. |
| API down | `502 {"detail":{"code":"api_unreachable","message":"The API at <base> did not answer: <reason>"}}`. |

### Client (`src/lib/api/client.ts`)

| Function | Use |
|---|---|
| `apiGet<T>(path, params?, signal?)` | `GET /dashboard-api/api/<path>`. `path` has no `api/` prefix, for example `"overview"`. |
| `apiPost<T>(path, params?, body?, signal?)` | `POST`. `body` is JSON, or `Blob`/`FormData`/`string` for file upload. |
| `apiDelete<T>(path, params?)` | `DELETE`. |
| `apiHealth(signal?)` | `GET /dashboard-api/health`. HTTP 503 is not an error: the API sends a normal body when it is unhealthy. |
| `queryString(params)` | Leaves out empty values. An array repeats the key. |
| `ApiError {status, code, message}` | Error type. `parseError` maps `{"detail":{code,message}}`, `{"detail":"text"}`, and the 422 list. Network failure is `code: "network_error"`, `status: 0`. |

### Hooks (`src/lib/api/use-api.ts`)

| Hook | Use |
|---|---|
| `useQuery(key, fetcher, enabled?)` | One fetch for each key. A new key aborts the old request. Returns `{data, error, loading, reload}`. |
| `useApi(path, params?, {enabled?})` | `GET` with fixed parameters. |
| `useScopedApi(path, scope, extra?, {enabled?})` | `GET` with `site`, `from`, `to`, `class` from the global filters, plus `extra`. |
| `invalidate(prefix)` | Reload every mounted query whose key starts with `prefix`. |

### API calls that the UI makes

| UI use | Call |
|---|---|
| Site list (site selector) | `GET sites` |
| Overview and freshness | `GET overview` (+ `bucket=hour|day`) |
| Recommendations | `GET recommendations` (`run`, `pattern`, `confidence`, `change`), `GET recommendations/runs`, `GET recommendations/{id}`, `POST recommendations/generate?site=` |
| Agents | `GET agents` (`verification`, `q`), `GET agents/{agent_id}` |
| Activity | `GET events`, `GET events/{id}`, `GET sessions`, `GET sessions/{id}` |
| Pages and journeys | `GET pages` (`view` or `path`), `GET journeys`, `GET journeys/{id}` |
| Data and pipeline | `GET /health`, `GET imports`, `POST imports/upload?site=&source=`, `DELETE imports/{id}`, `GET runs`, `GET runs/{id}` |

The routes and response models are in [../api/README.md](../api/README.md). Calls made with `useScopedApi` (`overview`, `agents`, `agents/{id}`, `events`, `sessions`, `pages`, `journeys`, `journeys/{id}`) carry `site`, `from`, `to` and `class`. `agents/{id}` drops `class`. Calls made with `useApi` carry `site` only (or no parameter, for `sites` and `/health`).

### UI URLs

Each screen has a stable URL. The same data is available as JSON under `/api` (see [../api/README.md](../api/README.md)). Rules for the JSON side (label field, paging, stable sort) are in the api module.

```
 UI (browser)                                   Notes
 /overview                                      landing page; "/" also opens it
 /recommendations                               ?run=&pattern=&status=&confidence=
 /recommendations/{rec_id}                      list + detail sheet
 /agents  /agents/{agent_id}                    ?q=&verdict=
 /events  /events/{event_id}                    Events tab + filters
 /sessions  /sessions/{session_id}              Sessions tab + filters
 /pages                                         ?q=&preset=   (detail: ?detail=page:/path)
 /journeys  /journeys/{journey_id}              Journeys tab
 /data                                          ?tab=sources|imports|runs|health
                                                (detail: ?detail=run:{id} or ?detail=import:{id})
 any screen + ?detail=<type>:<id>               opens a detail sheet over the screen
 global on every URL                            ?site=&range=1h|6h|24h|7d&class=1,2,...
```

The full list of query parameters for each screen is in [screens.md](screens.md).

## Known limits

- Time range has four presets (1 h, 6 h, 24 h, 7 d). There is no custom range.
- The time range does not change the Recommendations list. A run has its own window (set by the API).
- No streaming or push. Screens load on open, on filter change, and on "Try again".
- Import detail finds a file in the newest 200 import files. An older file shows "Import file not found".
- The Sources table is built from the newest 200 import files. The API does not give the format or field map of a source.
- Import detail shows counts only. The API does not give reject line numbers, and the line text is not stored.
- The UI has no "force import again" action. Upload a file again to import it (a same-content file is reported as duplicate).
- Pipeline run detail shows counters per step. The API does not give the time of each step.
- Cleared alerts are not in the API. Data & pipeline shows open alerts only.
- Session detail shows "In progress" or "Closed". It does not show the age of the last event.
- The Activity events list has no timeline chart and no user-agent text search.
- The list API cannot filter by recommendation. With `?rec=<id>`, Activity lists the evidence IDs of that recommendation instead of a table.
- The Journeys tab only shows journeys in the site config. With none, it shows "No journeys configured".
- Only two test files exist (API client and filters, log-name parser). Screens have no automated test.
- No login. Anyone who can reach the dashboard server can use the API token through the proxy.

## Out of scope

- Login and access control (known gap, internal system; required before customer use).
- Editing config in the UI (files only).
- Live streaming and push updates (near real-time through the 1-minute runs is enough).
- Export, alerts by email or Slack, multi-site comparison.
- Visual design in these docs (the code in `src/app/styles/` is the source).

## Open questions

- Default time range: 24 h (current) or the recommendation window (6 h)?
- Do "Gone" recommendations show by default or only in run history? Current: they show in a separate panel "Gone since the previous run" under the list.

## How to change

| Task | Steps |
|---|---|
| Add a screen | Add an item in `shell/nav-config.ts`. Add a folder in `sections/`. Export it in `sections/index.ts`. Add a branch in `dashboard.tsx` (`view`). If it has tabs, add the extra view names to the `active` mapping there. Add a section in [screens.md](screens.md). |
| Add a global filter | Add it to `Scope` and `scopeFromQuery` / `scopeParams` in `src/lib/api/filters.ts`. Add the key to `globalKeys` in `dashboard.tsx`. Add the control in `shell/filter-bar.tsx`. Update `src/lib/api/api.test.mjs`. |
| Add a screen filter | Read it with `filters.get(...)` in the screen. Pass it as an API parameter. Show a chip or a control for it. Add it to the "Not applied on this tab" lists if the other tab ignores it. Add the parameter to [screens.md](screens.md). |
| Add a detail sheet | Add `details/<name>.tsx`. Add the type in `detailTitle` and `DetailContent` (`details/index.tsx`). Open it with `open("<type>", id)`. Add a style file `styles/detail-<name>.css` and import it in `globals.css`. |
| Add an API call | Add or change the type in `src/lib/api/types.ts`. Use `useApi` or `useScopedApi`. Wrap the result in `ApiGate`. The proxy needs no change for new `/api/*` routes. |
| Show a new value | Wrap it in `NumberLink` (link to the evidence) and `Label` (Observed, Inferred, Unknown). Use `Gap` when the API sends `null`. |
| Change a class name or colour | Edit `src/lib/classes.ts`. Names must match [../classification/README.md](../classification/README.md). |
| Change the freshness chip | Edit `stateChip` in `shell/topbar.tsx`. The state names come from the API (`Freshness.state` in `types.ts`). |
| Change the proxy | Edit `src/app/dashboard-api/[...path]/route.ts`. Keep the path allow-list and `no-store`. Update the Interfaces table above. |
| Read Next.js docs | Read `node_modules/next/dist/docs/` first (`AGENTS.md`). |

## Tests

From `apps/dashboard`:

```sh
npm run lint && npm test && npm run build
```

- `npm test` runs `node --experimental-strip-types --test src/lib/api/api.test.mjs src/lib/log-name.test.mjs`.
- `src/lib/api/api.test.mjs`: `queryString`, `scopeFromQuery` (default range), `scopeParams` (window ends at now).
- `src/lib/log-name.test.mjs`: `parseLogName` (site, source, start, label; bad names give `null`).
- Run the UI with `npm run dev` (http://localhost:3000/overview). The API must run on `API_URL`.

## Related modules

- [../api/README.md](../api/README.md): routes, response models, JSON rules, `API_TOKEN`.
- [../classification/README.md](../classification/README.md): the six traffic classes, verdicts, confidence.
- [../recommendations/README.md](../recommendations/README.md): patterns P1 to P5, priority, text source.
- [../activity-reconstruction/README.md](../activity-reconstruction/README.md): sessions, journeys, gaps.
- [../pipeline/README.md](../pipeline/README.md): lanes, runs, freshness, alerts.
- [../ingestion/README.md](../ingestion/README.md): import files, upload, delete import, log file names.
- [../deployment/README.md](../deployment/README.md): dashboard image, Compose, Helm.
- [../architecture/README.md](../architecture/README.md): system overview.
