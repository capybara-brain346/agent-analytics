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

## Files in this folder

Site `example`, 2026-10-12 00:00Z to 2026-10-18 10:00Z. One CDN file and one origin file for each scenario and day (`<scenario>-d<DD>`). The data is fictional. IP ranges are documentation, test or sample vendor ranges, and they do not overlap between scenarios.

| Scenario | Content | Requests (CDN / origin lines) | Expected result |
|---|---|---|---|
| `humans` | Browsers: day curve, weekends lower, journeys (pricing → signup → confirm, docs), assets, 404s on old blog links | 157,208 / 157,208 | All paired. Human sessions, conversions. |
| `crawlers` | GPTBot, OAI-SearchBot, ChatGPT-User, PerplexityBot from sample vendor ranges; ClaudeBot, Claude-User; Googlebot, bingbot; Amazonbot, meta, CCBot, Bytespider | 103,526 / 103,526 | All paired. OpenAI and Perplexity bots VERIFIED by IP list; Anthropic bots CLAIMED. Googlebot and bingbot need reverse DNS: offline they stay unverified. |
| `spoof` | Fake Googlebot and GPTBot, a rotating scraper (530 IPs), tool clients probing `/admin`, `/.env` | 91,068 / 58,997 | 35 % blocked at the CDN (403, no origin line). Fake bots SPOOFED or UNVERIFIED. |
| `failures` | Verified and claimed agents: 403 on key pages, 404 dead links with retries, 500 on `/signup`, redirect loops, thin content, slow `/docs/api`. In every 6-hour window | 74,504 / 74,504 | All paired. Recommendation patterns. |
| `coverage` | Shared NAT and Cloudflare-egress IPs with many user agents; 10 % CDN bypass (origin only); origin log gap on 2026-10-15 09:00–13:00Z; `coverage-d16-resend` repeats 30 % of the 2026-10-16 CDN file | 70,671 / 73,084 | Bypass rows `cdn_bypass`; gap rows CDN only; resend lines counted as duplicates; overlap warning on the resend file. |
| `edge` | Parser edge cases: 2–5 % intended rejects (bad JSON, bad timestamps, future timestamps, bad status, a line over 64 KB), IPv6, HEAD/POST/OPTIONS/PUT, unicode and query paths. The 2026-10-14 origin file is plain `.log` | 19,827 / 19,827 | Rejects with reasons in each import file. Origin lines with `\"` in a quoted field are rejected: nginx writes a quote as `\x22`. |

Total: 85 files, about 18 MB compressed, about 1 million log lines. Files of different scenarios cover the same hours, so the import list shows an overlap warning between them. The request IDs are unique, so no event is counted twice.

## Load

- **Dashboard:** open Data & pipeline → Sources. Drop one or more files on the tab, or use Upload log files. Each file is one upload. A file that is already stored is a duplicate and is not added again.
- **CLI (agents, scripts):** from `apps/api`, run `uv run python -m src.cli import ../../samples/logs --now`. This imports every log file in the folder, in name order. Then run the fast lane to pair, verify, classify and build the views: `uv run python -m src.cli run-pipeline fast --site <site>`.

## Delete

Open the file in Data & pipeline → Imports and select **Delete import**. This removes the file's events and its file record. The views of the site are built again on the next fast-lane run. When the file has paired rows, the paired file of the other source is read again, so its own lines stay. After a delete, you can load the same file again.

The delete is refused (`409`) while a pipeline run of the site is active, while the file is importing, or when a paired file cannot be read again because cleanup removed its raw file (after `RAW_RETENTION_DAYS`, 7 days by default).

## Limits

- The timestamps in a file are fixed. The dashboard ranges count back from now, so old sample data falls out of the selected range.
- The cleanup job drops event partitions older than `EVENTS_RETENTION_DAYS` (30 days by default). Sample data older than that is removed at the next cleanup.
