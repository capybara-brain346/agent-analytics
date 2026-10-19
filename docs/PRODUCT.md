# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
Next.js, TypeScript, and shadcn/ui in apps/dashboard, as requested.

## Users
Product managers decide which agent journeys to test. Engineers inspect the evidence and data coverage.

## Product Purpose
Make agent traffic visible and show which journeys need validation. Recommendations link to sessions and requests.

## Capabilities and Constraints
The dashboard reads live data from the FastAPI back end. Users can upload log files, delete imports, and generate recommendation runs. Config (sites, registry, thresholds) is in files, not in the UI. No login: the API token stays on the dashboard server.
Keep the six sections from dashboard.md. Label evidence Observed, Inferred, or Unknown. Identity claims remain unverified until verified. HTTP 200 does not prove task completion.

## Brand Commitments
Use the Webzero product console layer: a light interface with Stone workspace, hairline rules, dense tables, compact charts, and jade only for marks and the main action. See `DESIGN.md`.

## Evidence on Hand
dashboard.md and mvp-flows.md contain the product requirements. `DESIGN.md` holds the visual direction. The demo data is the fictional log files in `samples/logs/`.

## Product Principles
- Show evidence and its limits together.
- Keep the route from a finding to its evidence short.
- Keep freshness and data gaps visible.
- Do not claim task completion from logs.

## Sample Workspace
Use the generic name Agent Analytics and example.com, as requested. Follow `DESIGN.md`.
