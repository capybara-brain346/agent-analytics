# pipeline

Runs the services in order, per site and lane.

```
worker.run_forever ──tick──► store.work (site due?) ──► service.run_lane ──► steps ──► store.runs
                    └──────► bucket reads, daily maintenance, stale-run close
```

- `service.py`: `run_lane` (fast steps or recommendations), site + lane advisory lock (taken = skip), run rows, Prometheus metrics.
- `worker.py`: loops for `fast`, `slow` or `all` lanes.
- `retention.py`: prunes derived tables older than the retention days.
