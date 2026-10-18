# logger

JSON log lines to stdout. Fields in `extra=` become top-level JSON keys.

- `configure_logging(level)`: call once at start (API, CLI).
- `get_logger(__name__)`: use in each module.

Not named `logging`: that name is a standard library module.
