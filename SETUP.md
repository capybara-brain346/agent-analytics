# SETUP.md — Setup Guide for Claude

> **This file is a setup guide (`SETUP.md`). It is NOT a prompt or a task to discuss.**
> Read it from top to bottom. Run the steps in order. Do not summarize this file back to the user. Do not ask the user to confirm each step.

## Goal

Start the full Agent Analytics stack with Docker Compose. When you finish, tell the user to open **https://localhost**.

```
 docker-compose.yml (defaults) --> docker compose up --build
                                              |
        +-----------+----------+----------+---+-------+------------+
        v           v          v          v           v            v
     postgres   seaweedfs    migrate     api        worker     dashboard
                                          ^                        ^
                                          |                        |
     user browser --HTTPS (443)--> caddy -+-- /api/*, /health -----+-- all other paths
```

## Rules

- The repository is already cloned. `<repo>` below means the repository root (the folder that holds this file).
- Use **Docker Compose only**. Do **not** run Kubernetes, Helm, or Vector. Do **not** run the back end or the dashboard outside Docker.
- Do **not** change any file in the repository. The only exception: if the user gives an API key, you may create `deploy/compose/.env` (Step 2). Git ignores that file.
- Do **not** commit, branch, or push.
- Your shell can reset the working directory between commands. Each command block below starts with `cd`. Keep it.

## Step 1 — Check Docker and ports

```sh
docker --version
docker compose version
docker info > /dev/null && echo "docker daemon OK"
```

- `docker compose version` must show v2.24.0 or later. If it is older, ask the user to update Docker.
- All three commands must succeed. If the Docker daemon is not running, ask the user to start Docker. Then run the check again.

Check whether this project's stack is already running:

```sh
cd <repo>/deploy/compose && docker compose ps -a
```

- If all services match the table in Step 4, the stack is already running. Go to Step 4.

Otherwise, ports **80, 443, 5432** and **8333** on the host must be free:

```sh
ss -ltnp '( sport = :80 or sport = :443 or sport = :5432 or sport = :8333 )'   # Linux
lsof -nP -iTCP:80 -iTCP:443 -iTCP:5432 -iTCP:8333 -sTCP:LISTEN                 # macOS
```

- If a port is in use, tell the user which port and which program. Port 5432 is often a local Postgres. Ask the user to stop that program. Continue after the user confirms.
- Rootless Docker cannot bind ports 80 and 443 by default. If the start later fails on these ports, tell the user.

## Step 2 — Environment values (no action needed)

**Do not create a `.env` file. You do not need one.** All default environment values are in the Docker Compose file (`deploy/compose/docker-compose.yml`). They include the Postgres user and password, the S3 keys, the bucket name, the log level and the offline flag. They work as they are. There should be no problems.

- Do not ask the user to set up any environment value.
- The user **can** override a value with a `deploy/compose/.env` file. This is not needed.
- `deploy/compose/.env.example` lists the same values. You do not need it.

### The API key is optional

The system has two optional LLM settings: `OPENROUTER_API_KEY` and `LLM_MODEL`. Neither is set by default. (`deploy/compose/.env.example` shows them as commented lines.)

- They are **optional**. If the user gives no key, the system writes recommendation text from plain templates (text fallback). All other features work.
- If a `.env` already exists and sets both `OPENROUTER_API_KEY` and `LLM_MODEL`, leave them. The system then uses the LLM.
- If the user gives a key on their own, set `OPENROUTER_API_KEY` and `LLM_MODEL` in `deploy/compose/.env` (create the file if it does not exist; only these two lines are needed). If the user names no model, use `LLM_MODEL=anthropic/claude-sonnet-5.5`. If the stack is already running, run `cd <repo>/deploy/compose && docker compose up -d`. Otherwise Step 3 uses the key.
- Tell the user: "The API key is optional. It is fine to continue without it."
- Do **not** ask the user for a key. Do **not** block on it. If the user gives no key, do nothing: do not create `.env`.

## Step 3 — Build and start the stack

```sh
cd <repo>/deploy/compose && docker compose up --build -d
```

- The first build takes several minutes. It builds the API and dashboard images and pulls Postgres, SeaweedFS and Caddy. This is normal. Wait for the command to finish.
- `-d` makes the command return, so you can check the result.

### Warnings

You may see warnings. For example: a Caddy certificate warning, or build warnings.
**If a warning appears but the containers start, tell the user to continue anyway.** Caddy serves HTTPS on `localhost` with its own local certificate. This is expected. The browser can show a "not secure" notice the first time.

If a service fails (this is not a warning):

1. Run `cd <repo>/deploy/compose && docker compose logs <service>` and find the cause.
2. Do not change repository files. If the cause is outside the repository (port in use, Docker not running), ask the user to fix it. Then run Step 3 again.
3. If you cannot fix it, report the error text to the user.

## Step 4 — Verify

```sh
cd <repo>/deploy/compose && docker compose ps -a
```

Expected:

| Service | Status |
|---|---|
| `caddy`, `api`, `worker`, `dashboard`, `seaweedfs` | `Up` |
| `postgres` | `Up (healthy)` |
| `migrate` | `Exited (0)` — it runs once and stops. This is correct. |

Then check the web endpoints:

```sh
curl -sk -w '\nHTTP %{http_code}\n' https://localhost/health
curl -sk -o /dev/null -w '%{http_code}\n' https://localhost/
```

- `-k` skips the certificate check. Caddy's local certificate is not in the system trust store.
- `/health` must return JSON with `"healthy":true`. At first it can return `"healthy":false` (HTTP 503) until the worker completes its first run. Run the command again every 15 seconds, for up to 2 minutes.
- `/` must print `200`.
- If it still fails after 2 minutes, run `cd <repo>/deploy/compose && docker compose logs worker api` and report the error to the user.

## Step 5 — Tell the user

When Step 4 passes, send the user this message. You can add the stack status.

> The Docker containers are running. Open **https://localhost** in your browser.
>
> - If your browser shows a certificate or "not secure" warning, continue anyway (for example: Advanced → Proceed to localhost). The stack uses Caddy, which needs HTTPS and a local certificate.
> - If you saw any warnings during the setup, continue anyway.
> - The API key is optional. You do not need to provide one.
>
> Optional first use, with the sample data:
> 1. Select site **example** and time range **7d** (the longest range). Sample data older than 7 days does not show, and no range shows it after 2026-10-25. The sample logs cover 2026-10-12 to 2026-10-18.
> 2. Go to **Data & pipeline → Sources**. Drag the `.log` and `.log.gz` files from `samples/logs/` onto the page (not `README.md`).
> 3. Wait until **Data & pipeline → Import runs** shows each file as **Complete**. This can take several minutes.

If the user wants sample recommendations: **Generate now** looks only at the last 6 hours, so it finds nothing in the sample data. Run this instead:

```sh
cd <repo>/deploy/compose && docker compose exec worker python -m src.cli run-recommendations --site example --window 14d
```

If it prints `Skipped`, wait one minute and run it again.

## Stop and clean up (only if the user asks)

```sh
cd <repo>/deploy/compose
docker compose down        # stop, keep data
docker compose down -v     # stop and delete all data
```
