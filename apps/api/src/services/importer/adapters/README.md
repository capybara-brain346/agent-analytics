# adapters

Log line parsers. Each returns `ParsedLine` or `Reject` (see `__init__.py`).

| File | Source |
|---|---|
| `origin.py` | nginx-style origin access log (regex). Optional request-ID header for pairing. |
| `cdn.py` | CDN JSON / CSV / TSV. Field names come from `config/cdn/<vendor>.yaml`, not code. |
| `common.py` | Shared validation: length caps, IP, method, int ranges. |

New CDN vendor = new YAML field map. New log shape = new adapter here.
