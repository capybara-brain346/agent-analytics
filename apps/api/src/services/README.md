# services

Business logic. One folder per service: `service.py` + private helpers. `__init__.py` exports the public API:

```python
from src.services import importer
await importer.import_due_files(conn, site_id)
```

Fast lane order (each step is `(conn, site_id) -> counts dict`):

```
importer → pairing → verify → classify → reconstruction      (pipeline, FAST_STEPS)
recommendations                                               (pipeline, slow lane)
```

Support: `ingest` (HTTP upload), `site_config`, `registry`, `alerts`, `cleanup`.
No SQL here. Use `src/store`.
