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
