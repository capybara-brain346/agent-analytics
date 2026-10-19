# Agent Analytics

The Agent Analytics dashboard. Next.js, TypeScript, shadcn/ui, Base UI, and Lucide icons. It reads live data from the FastAPI back end (`apps/api`).

## Run

From `apps/dashboard`:

```sh
npm install
npm run dev
```

Open http://localhost:3000/overview. The API must run on `API_URL` (default http://localhost:8000). See `.env.example` and `../api/README.md`.

## Checks

```sh
npm run lint
npm test
npm run build
```

## Scope

Six sections: Overview, Recommendations, Agents, Activity explorer, Pages & journeys, and Data & pipeline. Filters (site, time range, class) are in the URL.

```
 browser ──► /dashboard-api/api/* ──► Next.js route handler ──► ${API_URL}/api/*
             (same origin)            adds Bearer API_TOKEN       (FastAPI)
```

- All data comes from the API. The browser never sees `API_URL` or `API_TOKEN` (`src/app/dashboard-api/[...path]/route.ts`).
- Actions: upload log files (button or drag and drop on Data & pipeline → Sources), delete an import, and generate a recommendation run.
- No login. Access control is the API token on the server side.

Product requirements are in `../../docs/dashboard.md` and `../../docs/mvp-flows.md`.

## Styling

The UI follows the Webzero product console layer (light theme, Instrument Sans and JetBrains Mono through `next/font/google`). `src/app/globals.css` only imports the files in `src/app/styles/`:

- `tokens.css`: Webzero tokens and the Tailwind `@theme` mapping for shadcn utilities.
- `base.css`, `shell.css` (rail, top bar, workspace, status row), `controls.css`, `panels.css`, `table.css`, `chart.css`, `detail.css`: shared rules.
- `detail-*.css`: one file per detail sheet.
- `focus.css`: keyboard focus (`:focus-visible`) as a background wash on every control and table row. Loaded last.
- `overview.css`, `recommendations.css`, `agents.css`, `activity.css`, `pages.css`, `data.css`: section-specific rules only.

Traffic-class chart colours are in `src/lib/classes.ts`. Visual rules are in `../../docs/DESIGN.md`.

## File map

Under `src/components/dashboard/`:

- `dashboard.tsx`: app frame, routing between sections, global filters.
- `shared.tsx`, `trend-chart.tsx`: shared building blocks (panel, pills, tables, charts).
- `shell/`: rail, top bar, filter bar, detail sheet host, nav config.
- `overview/`: Overview panels (metrics, classes, top pages, recommendations, coverage).
- `sections/`: one screen each.
  - `agents.tsx`
  - `activity/`: events and sessions tables, toolbar, pager, recommendation evidence bar.
  - `data-pipeline/`: health, imports, runs, and sources tabs. `upload.tsx`: multi-file upload and the drop zone on the Sources tab.
  - `pages-journeys/`: pages and journeys tabs.
  - `recommendations/`: table, status, and run controls.
- `details/`: detail sheets per entity. `common.tsx` has the shared sections and fields, `facts.tsx` the fact lists, `legend.tsx` the chart legend.
