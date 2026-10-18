# Sample logs

Test data for development, demos and tests. The data is these log files, not rows inserted into the database. Load the files you need, delete them when you are done, and load them again later.

```
samples/logs/*.log(.gz)
   │  drag and drop on Data & pipeline → Sources, or the CLI
   ▼
POST /api/imports/upload ─► inbox ─► import_files (new, backfill)
   │                                    │  normal pipeline (fast lane)
   ▼                                    ▼
Delete import (detail sheet) ◄── events ─► sessions, pages, agents
```

## File name rule

```
<site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log[.gz]
example__cdn__20261001T0000Z__gptbot-burst.log.gz
```

| Part | Value |
|---|---|
| `site` | A site ID from `apps/api/config/sites/`. Letters, digits, `-` and single `_`. |
| `source` | `cdn` or `origin`. It must be a source of that site. |
| `YYYYMMDDTHHMMZ` | UTC time of the first line. It sorts the files. The import uses the timestamp on each line. |
| `label` | Optional. What the file shows. |

A dropped file gives the browser its name only, not its folder. So the site and source are in the name. A file whose name does not follow the rule uses the site and source that are selected in the dashboard.

## Load

- **Dashboard:** open Data & pipeline → Sources. Drop one or more files on the tab, or use Upload log files. Each file is one upload. A file that is already stored is a duplicate and is not added again.
- **CLI (agents, scripts):** from `apps/api`, run `uv run python -m src.cli import ../../samples/logs --now`. This imports every log file in the folder, in name order. Then run the fast lane to pair, verify, classify and build the views: `uv run python -m src.cli run-pipeline fast --site <site>`.

## Delete

Open the file in Data & pipeline → Imports and select **Delete import**. This removes the file's events and its file record. The views of the site are built again on the next fast-lane run. When the file has paired rows, the paired file of the other source is read again, so its own lines stay. After a delete, you can load the same file again.

The delete is refused (`409`) while a pipeline run of the site is active, while the file is importing, or when a paired file cannot be read again because cleanup removed its raw file (after `RAW_RETENTION_DAYS`, 7 days by default).

## Limits

- The timestamps in a file are fixed. The dashboard ranges count back from now, so old sample data falls out of the selected range.
- The cleanup job drops event partitions older than `EVENTS_RETENTION_DAYS` (30 days by default). Sample data older than that is removed at the next cleanup.
