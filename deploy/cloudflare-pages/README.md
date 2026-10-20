# Live-site test: Cloudflare Pages

Test the pipeline on a real site (piyushc.com) with real AI agents, without a CDN log contract.

## Why a capture and not an export

Cloudflare keeps no per-request log on the Free and Pro plans. Logpush (HTTP requests) is
Enterprise only. Instant Logs is Business and up. Analytics has no IP or user agent for each
request. So we capture each request at the time it occurs, and you cannot export the log after the test.

```
 Agent ── HTTPS ──► Cloudflare edge ──► functions/_middleware.js ──► Pages site
                                              │ console.log({log: "request_log", ...})
                                              ▼
                         wrangler pages deployment tail --search request_log
                                              │ capture.sh (30 min or Ctrl-C)
                                              ▼
                  captures/piyushc__cdn__<start>__<label>.log   (one JSON line for each request)
                                              │ cli import --now
                                              ▼
                  importer (config/cdn/cloudflare.yaml) ──► pipeline ──► dashboard ?site=piyushc
```

The middleware lives in the site repository (`personal-website/functions/_middleware.js`). It
writes the fields of `apps/api/config/cdn/cloudflare.yaml`, plus `asn` and `country`, which the
importer ignores. Logging cannot change or fail a response.

## Files

| File | Purpose |
|---|---|
| `capture.sh` | Tails the newest production deployment; after `CAPTURE_MINUTES` (default 30) or on Ctrl-C writes the log file |
| `site/piyushc.yaml` | Site config: one source (`cdn`), key pages, chatbot and voice as conversions |
| `site/piyushc-pages.txt` | Pages from the site's sitemap, for pattern P4 |
| `apps/api/config/cdn/cloudflare.yaml` | Field map for the middleware lines |

The site files stay out of `apps/api/config/sites/`: with two sites, the API needs `?site=` on
each call and the dashboard has no site picker yet. Tests always use only the `example` site
(`tests/conftest.py`).

## Run a test

Needs: `wrangler` logged in to the account that owns the Pages project, `jq`, the local stack
(`apps/api/README.md`).

1. **Turn off the zone cache.** Cloudflare dashboard → piyushc.com → Caching → Configuration →
   Development Mode → On. It turns itself off after 3 hours. Without it, cache hits (for example
   `/`) never reach the middleware and are missing from the log.
2. **Copy the site files** (git ignores the copies):

   ```sh
   cp deploy/cloudflare-pages/site/* apps/api/config/sites/
   ```

3. **Start the capture** before the first agent:

   ```sh
   deploy/cloudflare-pages/capture.sh piyushchoudhari-me piyushc <label>
   ```

4. **Check the capture.** In JSON mode, wrangler prints no "connected" message. Open
   `https://piyushc.com/` twice in a browser, then run `grep -c request_log captures/*.tail.json`.
   The count must go up by 2. If it goes up by 1, Development Mode is off. Start the agents only
   after this check.
5. **Run the agents** with one open-ended prompt, the same for each agent
   (`docs/modules/testing/real-site-test.md`, "Agent run"). Run them all inside the capture window. You
   check the results by hand against the runs you know.

6. **Stop the capture.** It stops by itself after 30 minutes. Set `CAPTURE_MINUTES=<n>` before the
   command for another limit, or press Ctrl-C to stop early. The script prints the line count and
   the log path. If the tail ends before the limit, the script prints a warning with the elapsed
   time and the exit code. The tail's error output is in `<file>.log.tail.json.err`.
7. **Import and run the pipeline** (from `apps/api`):

   ```sh
   uv run python -m src.cli import ../../captures/<file>.log --now
   uv run python -m src.cli run-pipeline fast --site piyushc
   uv run python -m src.cli run-recommendations --site piyushc
   ```

8. **Check** the dashboard (`/?site=piyushc`) by hand against the runs you know.

## Known limits

| Limit | Effect | Mitigation |
|---|---|---|
| Zone cache hits skip the middleware | Missing requests | Development Mode during the test (step 1) |
| Tail samples under high load; a lost connection loses lines | Missing requests | Low traffic site; keep the terminal open |
| Each request (also assets) is a Functions call | Free plan: 100,000 calls a day | Enough for test runs |
| `bytes` is 0 | Pages streams without `content-length` | None; the pipeline does not need bytes |
| No bot score | `edge_signal` is `none` | Classification uses user agent and IP lists only |
| Unknown paths return 200 with the homepage | A guessed URL looks like a success | A finding about the site, not a capture fault |
| Cal.com link and voice provider calls leave the domain | Not visible | Only `/api/assistant` and `/api/assistant-voice` show |
| Log lines hold real visitor IP addresses | Personal data | `captures/` is git-ignored; never commit captures |
