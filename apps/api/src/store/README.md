# store

The only module with SQL (psycopg 3, no ORM) and S3 access. Routes and services call these functions.

| File | Content |
|---|---|
| `db.py` | Connection pool. |
| `inbox.py` | S3 inbox: put, stream lines, gunzip. |
| `import_files.py` | Import file state machine and rejects. |
| `events.py` | `COPY` into daily `events` partitions; partition create / drop. |
| `pairing.py`, `verdicts.py`, `classify.py`, `ip_lists.py` | Pairing, verify and classify data. |
| `views.py` | Activity reconstruction: sessions + hourly rollups (incremental, see notes at top). `reset_site`: full rebuild after a delete. |
| `recommendations.py` | Recommendation pattern queries and run / item rows. |
| `runs.py`, `work.py`, `locks.py` | Pipeline runs, due-site queue, advisory locks. |
| `alerts.py`, `quota.py`, `retention.py` | Alerts, ingest byte quota, pruning. |
| `queries.py` | Read queries for the dashboard routes. |
