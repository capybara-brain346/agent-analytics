# Real-site test

This file describes how we test Agent Analytics on a real website with real AI agents. It covers the approach, the capture tools and the procedure. The test results are in a separate report (Linear ZER-244).

Tracking: Linear ZER-237 (parent ZER-236). Code: PR #4 and PR #5 (`agent-analytics`), commit `543a16b` (`personal-website`).

## Read this when

- You run the real-site test.
- You change `deploy/cloudflare-pages/` (`capture.sh`, site files) or `apps/api/config/cdn/cloudflare.yaml`.
- You add another live test site.
- You write the results report (ZER-244).

## Code map

| Path | Purpose | In git |
|---|---|---|
| `deploy/cloudflare-pages/capture.sh` | Capture script. | Yes |
| `deploy/cloudflare-pages/README.md` | Run book. | Yes |
| `deploy/cloudflare-pages/site/piyushc.yaml` | Site config (see "Site config"). | Yes |
| `deploy/cloudflare-pages/site/piyushc-pages.txt` | 21 pages from the site's sitemap, for pattern P4. | Yes |
| `apps/api/config/cdn/cloudflare.yaml` | Field map for the middleware lines. No `edge_bot` block: the Free plan has no bot score. | Yes |
| `apps/api/config/sites/piyushc.yaml`, `piyushc-pages.txt` | Local copies for a test run. | No (git-ignored: `apps/api/config/sites/piyushc*`) |
| `captures/` | Capture files with real visitor IPs. | No (git-ignored) |
| `.wrangler/` | Cloudflare account cache. | No (git-ignored) |
| `personal-website/functions/_middleware.js` | The middleware. It lives in the site repository, not in this repository. | Site repo |
| `apps/api/src/routes/sites.py` | `GET /api/sites`: the site list for the dashboard selector. | Yes |
| `apps/api/tests/conftest.py` | `base_config_dir`: tests ignore local site files. | Yes |

## Purpose

The sample logs in `samples/logs/` are synthetic. They show that the pipeline works, but they cannot show how real agents behave. This test sends real agent traffic to a real site and runs it through the full pipeline.

```
 real agents ──► real site ──► request log ──► importer ──► classify ──► activity
                                                                         reconstruction
                                                                              │
                              dashboard ◄── recommendations ◄─────────────────┘
```

The test answers these questions:

- Does the pipeline accept a real CDN-style log without rejects?
- Which classes, evidence and confidence does the pipeline give to real agents?
- Does activity reconstruction make sessions that match the real agent visits?
- Do the recommendations point to real problems on the site?
- Which agent activity can the logs not show?

## Approach

| Option | Decision | Reason |
|---|---|---|
| Connect a customer CDN and origin | Not used | It takes too much time for this sprint. |
| Use the synthetic sample logs | Not enough | They cannot show real agent behavior. |
| Test on a site that we control | **Used** | We control the site, the deploys and the agents, and we know what we ran. |

Test site: **piyushc.com**, the owner's personal site.

## Test site

| Property | Value |
|---|---|
| Stack | Astro 6, static output |
| Hosting | Cloudflare Pages, Free plan, git-connected (production deploys from `main`) |
| Pages project | `piyushchoudhari-me` |
| Domains | `piyushc.com`, `content.piyushc.com`, `piyushchoudhari-me.pages.dev` |
| Edge cache | HTML and assets have `s-maxage=31536000` (`public/_headers`). The zone cache serves some requests. |

Content and features that agents can reach:

| Feature | Path | Visible in the log |
|---|---|---|
| Home page | `/` | Yes |
| Blog index and 15 posts | `/blog`, `/blog/<slug>` | Yes |
| Projects index and 3 projects | `/projects`, `/projects/<slug>` | Yes |
| Markdown versions | `/blog/<slug>.md`, `/projects/<slug>.md` | Yes |
| Machine-readable files | `/llms.txt`, `/llms-full.txt`, `/robots.txt`, `/rss.xml`, `/sitemap-index.xml` | Yes |
| Search and command palette data | `/cmdk-data.json` | Yes |
| Chatbot | `POST /api/assistant` | Yes |
| Voice assistant | `/api/assistant-voice` | The first request only. A WebSocket or third-party provider is not visible. |
| View counters and upvotes | `GET`/`POST /api/counter` | Yes |
| Booking | Link to `cal.com` | **No**: the request goes to another domain |

## Capture design

### Why a live capture, not a log export

Cloudflare keeps no per-request log on the Free plan. So we cannot export the logs after the test. We must capture each request while it occurs.

| Cloudflare source | What it gives | Plan | Usable |
|---|---|---|---|
| Logpush (HTTP requests) | Every request, all fields | Enterprise | No |
| Instant Logs | Live stream of every request | Business and up | No |
| Analytics (dashboard, GraphQL) | Sampled counts, no IP or user agent for each request | Free | No |
| Security Events | Only requests that a firewall rule matched | Free | No |
| **Pages Functions middleware + `wrangler tail`** | One line for each request, the fields we choose | Free | **Yes** |

Cloudflare is the precedent for this test. The pipeline does not depend on it: any source that writes one JSON line for each request with a field map in `apps/api/config/cdn/` works.

### Middleware

`personal-website/functions/_middleware.js` runs for every request: pages, static assets and `/api/*`. It calls `context.next()` without change and then writes one structured line to the Functions log.

| Field | Source |
|---|---|
| `log` | Always `request_log` (the filter key for the capture) |
| `request_id` | `cf-ray` header |
| `timestamp` | Time when the request started (ISO 8601, UTC) |
| `client_ip` | `cf-connecting-ip` header |
| `method`, `host`, `path` | Request URL (the path includes the query string) |
| `status` | Response status |
| `bytes` | Response `content-length` (0 when Pages streams the response) |
| `user_agent`, `referrer` | Request headers |
| `asn`, `country` | `request.cf` (the importer ignores these fields) |

Safety rules:

- Logging is in `try/catch`. A logging error cannot change or fail a response.
- An error from `context.next()` is logged as status 500 and then thrown again, as before.

### Capture flow

```
 Agent            Cloudflare edge        _middleware.js         Pages site        capture.sh
   │                     │                     │                    │           (wrangler tail)
   │── GET /blog/x ─────►│                     │                    │                 │
   │                     │── run function ────►│                    │                 │
   │                     │                     │── context.next() ─►│                 │
   │                     │                     │◄── 200 + HTML ─────│                 │
   │                     │                     │── console.log(request_log) ─────────►│ append to
   │◄──── 200 + HTML ────│◄────────────────────│                    │                 │ *.tail.json
```

### `capture.sh`

Usage: `deploy/cloudflare-pages/capture.sh <project> <site> [label] [out_dir]`. Default `label`: `run`. Default `out_dir`: `captures`.

Needs: `wrangler` (run through `npx --yes`) logged in to the account that owns the Pages project, and `jq`.

1. Finds the newest production deployment of the Pages project (`wrangler pages deployment list --environment production --json`, first entry).
2. Runs `wrangler pages deployment tail --format json --search request_log` and writes the output to `captures/<site>__cdn__<start>__<label>.log.tail.json`. The tail's error output goes to the terminal and to `<file>.log.tail.json.err`.
3. After `CAPTURE_MINUTES` (default 30) or on Ctrl-C, stops the tail only. The time limit and Ctrl-C both send SIGINT to the tail; the script continues.
4. Extracts each `request_log` object with `jq`, removes the `log` key, and writes `captures/<site>__cdn__<start>__<label>.log` (one JSON line for each request).
5. Prints the line count and the path. If the tail ends more than 5 seconds before the limit, it prints a warning with the elapsed time and the exit code.

The file name follows the importer rule `<site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log`, so the CLI and the dashboard upload find the site and the source from the name.

## Agent Analytics configuration

### Data flow into the pipeline

```
 captures/piyushc__cdn__<start>__<label>.log
        │  cli import --now   or   dashboard upload (Data & pipeline)
        ▼
 inbox (S3) ──► importer ──► config/cdn/cloudflare.yaml (field map) ──► events
        │                                                                  │
        │              config/sites/piyushc.yaml (local copy)              ▼
        └──────────────────────────────────────────────► classify ──► sessions ──► recommendations
                                                                                       │
                                                         dashboard /?site=piyushc ◄────┘
```

### Field map (`apps/api/config/cdn/cloudflare.yaml`)

| Key | Value |
|---|---|
| `format` | `json` |
| `edge_request_id` | `request_id` (`cf-ray`) |
| `timestamp` | `timestamp` |
| `client_ip` | `client_ip` (`cf-connecting-ip`) |
| `method`, `path`, `status`, `bytes`, `user_agent`, `host`, `referrer` | Same name as the log field |
| `edge_bot` | Not set: the bot score needs Cloudflare Bot Management |

### Site config (`piyushc.yaml`)

| Key | Value | Reason |
|---|---|---|
| `site_id` | `piyushc` | Site ID in the file name and `?site=`. |
| `sources` | `[cdn]` | Pages has no origin server, so there is nothing to pair. |
| `cdn_field_map` | `cloudflare` | The middleware format. |
| `key_pages` | `/`, `/blog`, `/projects`, `/llms.txt`, `/llms-full.txt` | The pages that tell an agent who the owner is. |
| `conversion_pages` | `/api/assistant`, `/api/assistant-voice` | Use of the chatbot or voice is the strongest action visible in the log. |
| `access_policy.allow` | `/llms.txt`, `/llms-full.txt` | `robots.txt` blocks nothing. |
| `site_pages` | `{file: piyushc-pages.txt}` | Pages that agents could reach but never visit (pattern P4). |
| `no_data_alert_minutes` | `1440` | Data arrives only during test runs. |
| `journeys` | None | The booking leaves the domain, so the log cannot show a journey end. |

The site files stay out of the shipped `apps/api/config/sites/` so that the demo stays single-site. For a test run, copy them in and rebuild the Compose stack (the API image copies `config/` at build time).

### Product changes that the test needed

| Change | Why | Where |
|---|---|---|
| `GET /api/sites` and a site selector that lists all sites | With two sites, every screen failed with `site_required` (HTTP 422). The selector showed only the current site. | PR #5 |
| A URL without `site` opens the first site | Old links keep working. | PR #5 |
| Tests use a config copy with only the `example` site | A local `piyushc` file made 39 tests fail. | PR #4, `tests/conftest.py` |
| `.gitignore`: `captures/`, `.wrangler/`, local site copies | Real visitor IPs and the Cloudflare account cache must not go into git. | PR #4 |

## Setup checks before the agent run

These checks prove that the capture and the import work. They are not test results.

| Check | Method | Outcome |
|---|---|---|
| The middleware logs every request type | Preview deployment, 9 requests (page, redirect, asset twice, `llms.txt`, `robots.txt`, unknown path, query string, API) | All 9 captured |
| Cache behavior on production | The same URLs requested 2-3 times on `piyushc.com`, `cf-cache-status` compared with the log | `HIT` responses are **not** logged. `MISS`, `EXPIRED` and `DYNAMIC` are logged. |
| The capture script | Script started, 3 requests sent, stopped with SIGINT | `.log` written with the right lines |
| CLI import | Smoke file through `cli import --now` and `run-pipeline fast` | 15/15 lines, 0 rejects, sessions classified |
| Dashboard upload | Capture file uploaded on Data & pipeline | Imported, 0 rejects |
| Dashboard with two sites | Playwright on the Compose stack | `/` opens `?site=example`, the selector lists both sites, `piyushc` loads, no 422 |

## Procedure

```
 1 Development Mode ON ──► 2 copy site files ──► 3 start capture ──► 4 check capture
                                                                          │
 8 open dashboard ◄── 7 import + pipeline ◄── 6 stop capture ◄── 5 run agents
```

1. **Turn off the zone cache.** Cloudflare dashboard, piyushc.com, Caching, Configuration, Development Mode, On. It switches itself off after 3 hours. Without it, cache hits (for example `/`) are missing from the log. The wrangler token has zone read access only, so a person must do this step.
2. **Copy the site files** and rebuild the stack: `cp deploy/cloudflare-pages/site/* apps/api/config/sites/` and then `docker compose up --build -d` from `deploy/compose`.
3. **Start the capture** from the repository root, before the first agent: `deploy/cloudflare-pages/capture.sh piyushchoudhari-me piyushc <label>`.
4. **Check the capture.** In JSON mode, wrangler prints no "connected" message. Open `https://piyushc.com/` twice and run `grep -c request_log captures/*.tail.json`. The count must go up by 2. If it goes up by 1, Development Mode is off. Start the agents only after this check.
5. **Run the agents** (see "Agent run"). Run them all inside the capture window. Do not push to the site's `main` branch during the run: the script tails one deployment only.
6. **Stop the capture** about 1 minute after the last agent finishes (log lines arrive a few seconds late). The capture stops by itself after 30 minutes (`CAPTURE_MINUTES=<n>` sets another limit). Press Ctrl-C to stop early. The script prints the line count and the file path.
7. **Import and run the pipeline:** upload the `.log` file on Data & pipeline, or from `apps/api` run:

   ```sh
   uv run python -m src.cli import ../../captures/<file>.log --now
   uv run python -m src.cli run-pipeline fast --site piyushc
   uv run python -m src.cli run-recommendations --site piyushc
   ```

8. **Open the dashboard** at `https://localhost/?site=piyushc` and check it by hand against the runs you know.

## Agent run

Each agent gets the same short, open-ended prompt. We do not give fixed tasks or URLs, because real agents arrive with their own goals and do not follow a script:

```text
Visit https://piyushc.com and browse it like a normal person would. Look around, open whatever
catches your interest, read some of it, and try out anything on the site that looks interactive.
Take your time. When you're done, tell me briefly what you found.
```

The owner chooses the agents and runs them. The results report lists the agents and the time windows.

## Evaluation method

There is no formal ground-truth sheet. The runs are our own test traffic, so the owner knows what ran and checks the pipeline output by hand.

| Area | What the owner checks |
|---|---|
| Import | Lines imported, rejected and duplicate for each capture |
| Classification | Class, evidence and confidence for each agent; agents that the pipeline missed or labeled wrongly |
| Activity reconstruction | Sessions compared with the real visits: start, end, pages; sessions split or merged |
| Recommendations | At least 3, each linked to evidence from the run |
| Blind spots | Agent activity that the log did not show |

Reporting rules (from ZER-236):

- Keep observed facts, inferences and unknowns separate.
- A crawler label does not prove intent. A 200 response does not prove that the agent completed a task.

## Runs

| Run | Start (UTC) | Purpose |
|---|---|---|
| smoke | 2026-10-19 07:07 | Preview and production capture checks (see "Setup checks") |
| run1 | 2026-10-19 07:26 | Capture check with the owner's own visits |
| run2 | 2026-10-19 07:29 | Capture check |
| run3 | 2026-10-19 07:44 | First agent traffic run |

The results are in the results report (ZER-244).

## Rules and decisions

1. Capture each request live. Do not plan a log export.
   Why: the Free plan keeps no per-request log.
2. Turn on Development Mode for each run.
   Why: zone cache hits skip the middleware and are missing from the log.
3. Use one open-ended prompt for every agent. Give no fixed tasks or URLs.
   Why: real agents have their own goals.
4. Evaluate by hand. Keep facts, inferences and unknowns separate (ZER-236).
   Why: the runs are our own traffic and there is no ground-truth sheet.
5. Keep site files for a live site out of the shipped `apps/api/config/sites/`. Copy them in for a run.
   Why: the demo stays single-site, and tests must not see them.
6. The middleware must not change a response. Logging errors stay inside `try/catch`.
   Why: the test site is a real site with real visitors.
7. Keep capture files on the test machine only. They never go into `samples/` or a commit.
   Why: they hold real visitor IP addresses and user agents (personal data).

## Known limits

| Limit | Effect | Mitigation |
|---|---|---|
| Zone cache hits skip the middleware | Missing requests | Development Mode during each run |
| The tail can sample under high load; a lost connection loses lines | Missing requests | Low-traffic site; keep the terminal open; check the count |
| Each request (also assets) is a Functions call | Free plan: 100,000 calls a day | Enough for test runs |
| `bytes` is 0 | No response size | The pipeline does not need bytes |
| No bot score on the Free plan | `edge_signal` is `none` | Classification uses user agent, IP lists and behavior only |
| Unknown paths return 200 with the home page | A guessed URL looks like a success | A finding about the site, not a capture fault |
| Booking on cal.com and voice provider traffic leave the domain | Not visible | Only `/api/assistant` and `/api/assistant-voice` show |
| One source (CDN), no origin | No pairing, no edge/origin comparison | Accepted for this test |
| Other visitors use the site during a run | Their requests are in the capture | Separate them by IP, user agent and time |
| The tail follows one deployment only | A push to `main` during a run moves traffic to a new deployment | Do not push during a run |
| Wrangler token has zone read access only | A script cannot switch Development Mode | A person does step 1 |

## Data handling

- Capture files hold real visitor IP addresses and user agents. They stay on the test machine in `captures/`, which git ignores. They never go into `samples/` or a commit.
- `.wrangler/` holds the Cloudflare account cache. Git ignores it.
- Development Mode changes only the cache, and only for 3 hours.
- The middleware does not change responses. It is in the site repository and can be removed by reverting commit `543a16b`.

## How to change

| Task | Steps |
|---|---|
| Add a site | Add `<site>.yaml` and `<site>-pages.txt` to `deploy/cloudflare-pages/site/` (or a new folder). Use `sources: [cdn]` and a `cdn_field_map` that exists in `apps/api/config/cdn/`. Add the local copy to `.gitignore` if the site is not shipped. |
| Use another log source | Add a field map in `apps/api/config/cdn/<name>.yaml`. Set `cdn_field_map: <name>` in the site file. Data change, no code change. |
| Change the capture limit | Set `CAPTURE_MINUTES=<n>` before `capture.sh`. |
| Change what the middleware logs | Edit `personal-website/functions/_middleware.js`, then the field map in `apps/api/config/cdn/cloudflare.yaml`. Keep logging inside `try/catch`. |
| Change the agent prompt | Edit "Agent run" here. Use the same prompt for every agent in a run. |

## Tests

No automated test runs the live capture. The setup checks above are manual. The test fixtures keep local `piyushc*` site files out of the unit tests (`base_config_dir` in `apps/api/tests/conftest.py`). Run the back end checks as in the [testing README](README.md#tests).

## Related modules

- [Testing README](README.md)
- [Ingestion](../ingestion/README.md)
- [Classification](../classification/README.md)
- [Activity reconstruction](../activity-reconstruction/README.md)
- [Recommendations](../recommendations/README.md)
- [Deployment](../deployment/README.md)
- [Dashboard](../dashboard/README.md)
