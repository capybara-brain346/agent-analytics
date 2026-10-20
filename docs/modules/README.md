# Modules

One folder for each module. Each folder has a `README.md` with the same sections: summary, read this when, code map, data flow, rules and decisions, configuration, interfaces, known limits, how to change, tests, related modules.

The code is the ground truth. If a module doc and the code disagree, fix the doc in the same change.

## Pipeline map

```
 CDN logs ─┐
           ├─▶ ingestion ─▶ pairing ─▶ verification ─▶ classification ─▶ activity-reconstruction
origin logs┘   (import)     (CDN+origin) (identity)     (6 classes)        (sessions, journeys)
                                                                                   │
                         fast lane (worker loop) ◀────────────────────────────────┘
                                                                                   │
        slow lane (every `recommendation_window`, default 6h) ──▶ recommendations ◀┘
                                                                                   │
                                       store (PostgreSQL + S3 inbox) ◀─────────────┤
                                                                                   ▼
                                                     api (FastAPI, CLI) ─▶ dashboard (Next.js)
```

## Index

| Module | Read it to |
|---|---|
| [architecture](architecture/README.md) | Understand the whole system, deployment targets, stack and repo map. Start here. |
| [ingestion](ingestion/README.md) | Change how log files arrive, are named, parsed, deduplicated or deleted. |
| [pairing](pairing/README.md) | Change how CDN and origin lines pair, or add a CDN field map. |
| [verification](verification/README.md) | Change agent identity checks, the bot registry or IP lists. Add a bot. |
| [classification](classification/README.md) | Change the 6 traffic classes, rules or confidence. |
| [activity-reconstruction](activity-reconstruction/README.md) | Change sessions, journeys or page aggregates. |
| [recommendations](recommendations/README.md) | Change recommendation patterns, scoring, text or site config. |
| [pipeline](pipeline/README.md) | Change the worker, lanes, locks, retention, cleanup or alerts. |
| [store](store/README.md) | Change tables, migrations or SQL access. |
| [api](api/README.md) | Change routes, the CLI or settings. Central settings reference. |
| [dashboard](dashboard/README.md) | Change dashboard screens, UX rules or UI URLs. |
| [deployment](deployment/README.md) | Change Compose, Helm, Dockerfiles or log senders. |
| [testing](testing/README.md) | Run or add tests, use sample logs, run the real-site test. |
