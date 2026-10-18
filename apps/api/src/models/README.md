# models

Shared types. No I/O.

| File | Content |
|---|---|
| `domain.py` | Enums for DB values: lanes, verdicts, `TrafficClass` 1–6, patterns, statuses. |
| `api.py` | Pydantic response models shared by routes. Route-only models stay in the route file. |
| `keys.py` | `client_key(ua, ip)` and `normalize_ip`: the grouping key for a client. |
