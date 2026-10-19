#!/usr/bin/env bash
# Capture the request_log lines of a Cloudflare Pages site during a live test (README.md).
# Usage: capture.sh <pages-project> <site_id> [label] [out_dir]
# The capture stops after CAPTURE_MINUTES (default 30) or on Ctrl-C. The script then writes
# <out_dir>/<site>__cdn__<start>__<label>.log, ready for
# `uv run python -m src.cli import <file> --now`.
set -euo pipefail

project=${1:?pages project name}
site=${2:?site id}
label=${3:-run}
out=${4:-captures}
minutes=${CAPTURE_MINUTES:-30}

start=$(date -u +%Y%m%dT%H%MZ)
log="$out/${site}__cdn__${start}__${label}.log"
raw="$log.tail.json"
mkdir -p "$out"

deployment=$(npx --yes wrangler pages deployment list --project-name "$project" \
  --environment production --json | jq -r '.[0].Id')
echo "Tailing deployment $deployment of $project for $minutes minutes. Stop early with Ctrl-C." >&2

# The time limit and Ctrl-C both send SIGINT to the tail only; the script continues and converts
# the capture. --foreground keeps the tail in the terminal's process group, so Ctrl-C reaches it.
trap 'true' INT
timeout --foreground -s INT "${minutes}m" \
  npx --yes wrangler pages deployment tail "$deployment" --project-name "$project" \
  --format json --search request_log > "$raw" || true
trap - INT

jq -c '.logs[]?.message[0] | select(type == "object" and .log == "request_log") | del(.log)' \
  "$raw" > "$log"
echo "$(wc -l < "$log") requests -> $log" >&2
