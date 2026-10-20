# Real-site test: approach

This document describes how we test Agent Analytics on a real website with real AI agents. It
describes the approach only. The test results are in a separate report (Linear ZER-244).

Tracking: Linear ZER-237 (parent ZER-236). Code: PR #4 and PR #5 (agent-analytics), commit
543a16b (personal-website).

## 1. Purpose

The sample logs in `samples/logs/` are synthetic. They show that the pipeline works, but they
cannot show how real agents behave. This test sends real agent traffic to a real site and runs it
through the full pipeline:

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

## 2. Why this approach

| Option | Decision | Reason |
|---|---|---|
| Connect a customer CDN and origin | Not used | It takes too much time for this sprint. |
| Use the synthetic sample logs | Not enough | They cannot show real agent behavior. |
| Test on a site that we control | **Used** | We control the site, the deploys and the agents, and we know what we ran. |

Test site: **piyushc.com**, the owner's personal site.

## 3. The test site

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

## 4. Capture design

### 4.1 Why a live capture, not a log export

Cloudflare keeps no per-request log on the Free plan. So we cannot export the logs after the test.
We must capture each request while it occurs.

| Cloudflare source | What it gives | Plan | Usable |
|---|---|---|---|
| Logpush (HTTP requests) | Every request, all fields | Enterprise | No |
| Instant Logs | Live stream of every request | Business and up | No |
| Analytics (dashboard, GraphQL) | Sampled counts, no IP or user agent for each request | Free | No |
| Security Events | Only requests that a firewall rule matched | Free | No |
| **Pages Functions middleware + `wrangler tail`** | One line for each request, the fields we choose | Free | **Yes** |

### 4.2 Middleware

`personal-website/functions/_middleware.js` runs for every request: pages, static assets and
`/api/*`. It calls `context.next()` without change and then writes one structured line to the
Functions log:

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

### 4.3 Capture flow

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

`deploy/cloudflare-pages/capture.sh <project> <site> [label] [out_dir]`:

1. Finds the newest production deployment of the Pages project.
2. Runs `wrangler pages deployment tail --format json --search request_log` and writes the output
   to `captures/<site>__cdn__<start>__<label>.log.tail.json`.
3. After `CAPTURE_MINUTES` (default 30) or on Ctrl-C, stops the tail only, extracts each `request_log` object with `jq`, and writes
   `captures/<site>__cdn__<start>__<label>.log` (one JSON line for each request).

The file name follows the importer rule `<site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log`, so
the CLI and the dashboard upload find the site and the source from the name.

## 5. Agent Analytics configuration

### 5.1 Data flow into the pipeline

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

### 5.2 Files

| File | Content | In git |
|---|---|---|
| `apps/api/config/cdn/cloudflare.yaml` | Field map for the middleware lines. No `edge_bot` block: the Free plan has no bot score. | Yes |
| `deploy/cloudflare-pages/site/piyushc.yaml` | Site config, see 5.3 | Yes |
| `deploy/cloudflare-pages/site/piyushc-pages.txt` | 21 pages from the site's sitemap, for pattern P4 | Yes |
| `deploy/cloudflare-pages/capture.sh` | Capture script | Yes |
| `deploy/cloudflare-pages/README.md` | Run book | Yes |
| `apps/api/config/sites/piyushc*` | Local copies for a test run | No (git-ignored) |
| `captures/` | Capture files with real visitor IPs | No (git-ignored) |

### 5.3 Site config (`piyushc.yaml`)

| Key | Value | Reason |
|---|---|---|
| `sources` | `[cdn]` | Pages has no origin server, so there is nothing to pair |
| `cdn_field_map` | `cloudflare` | The middleware format |
| `key_pages` | `/`, `/blog`, `/projects`, `/llms.txt`, `/llms-full.txt` | The pages that tell an agent who the owner is |
| `conversion_pages` | `/api/assistant`, `/api/assistant-voice` | Use of the chatbot or voice is the strongest action visible in the log |
| `access_policy.allow` | `/llms.txt`, `/llms-full.txt` | robots.txt blocks nothing |
| `site_pages` | `piyushc-pages.txt` | Pages that agents could reach but never visit |
| `no_data_alert_minutes` | `1440` | Data arrives only during test runs |
| `journeys` | None | The booking leaves the domain, so the log cannot show a journey end |

The site files stay out of the shipped `apps/api/config/sites/` so that the demo stays single-site.
For a test run, copy them in and rebuild the Compose stack (the API image copies `config/` at
build time).

### 5.4 Product changes that the test needed

| Change | Why | Where |
|---|---|---|
| `GET /api/sites` and a site selector that lists all sites | With two sites, every screen failed with `site_required` (HTTP 422). The selector showed only the current site. | PR #5 |
| A URL without `site` opens the first site | Old links keep working | PR #5 |
| Tests use a config copy with only the `example` site | A local piyushc file made 39 tests fail | PR #4, `tests/conftest.py` |
| `.gitignore`: `captures/`, `.wrangler/`, local site copies | Real visitor IPs and Cloudflare account cache must not go into git | PR #4 |

## 6. Setup checks before the agent run

These checks prove that the capture and the import work. They are not test results.

| Check | Method | Outcome |
|---|---|---|
| The middleware logs every request type | Preview deployment, 9 requests (page, redirect, asset twice, `llms.txt`, `robots.txt`, unknown path, query string, API) | All 9 captured |
| Cache behavior on production | The same URLs requested 2–3 times on `piyushc.com`, `cf-cache-status` compared with the log | `HIT` responses are **not** logged. `MISS`, `EXPIRED` and `DYNAMIC` are logged. |
| The capture script | Script started, 3 requests sent, stopped with SIGINT | `.log` written with the right lines |
| CLI import | Smoke file through `cli import --now` and `run-pipeline fast` | 15/15 lines, 0 rejects, sessions classified |
| Dashboard upload | Capture file uploaded on Data & pipeline | Imported, 0 rejects |
| Dashboard with two sites | Playwright on the Compose stack | `/` opens `?site=example`, the selector lists both sites, `piyushc` loads, no 422 |

## 7. Test procedure

```
 1 Development Mode ON ──► 2 copy site files ──► 3 start capture ──► 4 check capture
                                                                          │
 8 open dashboard ◄── 7 import + pipeline ◄── 6 stop capture ◄── 5 run agents
```

1. **Turn off the zone cache.** Cloudflare dashboard → piyushc.com → Caching → Configuration →
   Development Mode → On. It switches itself off after 3 hours. Without it, cache hits are missing
   from the log. The wrangler token has zone read access only, so a person must do this step.
2. **Copy the site files** and rebuild the stack:
   `cp deploy/cloudflare-pages/site/* apps/api/config/sites/` and then
   `docker compose up --build -d` from `deploy/compose`.
3. **Start the capture** from the repository root:
   `deploy/cloudflare-pages/capture.sh piyushchoudhari-me piyushc <label>`.
4. **Check the capture.** In JSON mode, wrangler prints no "connected" message. Open
   `https://piyushc.com/` twice and run `grep -c request_log captures/*.tail.json`. The count must
   go up by 2. If it goes up by 1, Development Mode is off.
5. **Run the agents** (section 8). Do not push to the site's `main` branch during the run: the
   script tails one deployment only.
6. **Stop the capture** about 1 minute after the last agent finishes (log lines arrive a few
   seconds late). The capture stops by itself after 30 minutes (`CAPTURE_MINUTES=<n>` sets
   another limit); press Ctrl-C to stop early. The script prints the line count and the file path.
7. **Import and run the pipeline:** upload the `.log` file on Data & pipeline, or from `apps/api`
   run `uv run python -m src.cli import ../../captures/<file>.log --now`, then
   `run-pipeline fast --site piyushc` and `run-recommendations --site piyushc`.
8. **Open the dashboard** at `https://localhost/?site=piyushc`.

## 8. Agent run

Each agent gets the same short, open-ended prompt. We do not give fixed tasks or URLs, because
real agents arrive with their own goals and do not follow a script:

```text
Visit https://piyushc.com and browse it like a normal person would. Look around, open whatever
catches your interest, read some of it, and try out anything on the site that looks interactive.
Take your time. When you're done, tell me briefly what you found.
```

The owner chooses the agents and runs them. The results report lists the agents and the time
windows.

## 9. Evaluation method

There is no formal ground-truth sheet. The runs are our own test traffic, so the owner knows what
ran and checks the pipeline output by hand:

| Area | What the owner checks |
|---|---|
| Import | Lines imported, rejected and duplicate for each capture |
| Classification | Class, evidence and confidence for each agent; agents that the pipeline missed or labeled wrongly |
| Activity reconstruction | Sessions compared with the real visits: start, end, pages; sessions split or merged |
| Recommendations | At least 3, each linked to evidence from the run |
| Blind spots | Agent activity that the log did not show |

Reporting rules (from ZER-236):

- Keep observed facts, inferences and unknowns separate.
- A crawler label does not prove intent. A 200 response does not prove that the agent completed
  a task.

## 10. Runs

| Run | Start (UTC) | Purpose |
|---|---|---|
| smoke | 2026-10-19 07:07 | Preview and production capture checks (section 6) |
| run1 | 2026-10-19 07:26 | Capture check with the owner's own visits |
| run2 | 2026-10-19 07:29 | Capture check |
| run3 | 2026-10-19 07:44 | First agent traffic run |

The results are in the results report.

## 11. Known limits and blind spots

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

## 12. Data handling

- Capture files hold real visitor IP addresses and user agents. They stay on the test machine in
  `captures/`, which git ignores. They never go into `samples/` or a commit.
- `.wrangler/` holds the Cloudflare account cache. Git ignores it.
- Development Mode changes only the cache, and only for 3 hours.
- The middleware does not change responses. It is in the site repository and can be removed by
  reverting commit 543a16b.
