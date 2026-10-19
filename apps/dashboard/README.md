# Agent Analytics

A mock dashboard built with Next.js, TypeScript, shadcn/ui, Base UI, and Lucide icons.

## Run

From `apps/dashboard`:

```sh
npm install
npm run dev
```

Open http://localhost:3000/overview.

## Checks

```sh
npm run lint
npm test
npm run build
```

## Scope

Six sections: Overview, Recommendations, Agents, Activity explorer, Pages & journeys, and Data & pipeline. All values are fixed sample records for Oct 16, 2026. Links, filters, tabs, and evidence details work locally. Filters remain in the URL. The interface includes empty, stale, failed, unknown, and in-progress sample states.

No API, database, login, upload, job execution, scheduler, or external action is connected. Generation and upload controls explain that the workspace is read-only. Summary counts represent the larger fictional dataset; evidence tables show a small sample of its records.

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
