import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from psycopg import AsyncConnection

from src.config import get_settings
from src.logger import get_logger
from src.models.keys import client_key
from src.services import ingest
from src.services.importer.adapters import ParsedLine, Reject, cdn, origin
from src.services.importer.dedupe import line_key
from src.services.site_config import SiteConfig, load_site_config
from src.store import db, events, import_files
from src.store.inbox import Inbox, ObjectNotFound, get_inbox, is_missing

log = get_logger(__name__)

BATCH_ROWS = 5000
FUTURE_LIMIT = timedelta(days=1)
MAX_RETRIES = 5  # Transient inbox errors per file before it is failed
# A file is read in slices (Flow 7.9). A slice starts at the first line, so it reads and skips the
# lines done before (a gzip stream has no random access). To keep that cost bounded, the slice of
# one file grows with its progress: it takes at least as many lines as are done, up to
# SLICE_GROWTH_CAP times the work limit. A file of N lines needs about log2 slices at first and N
# divided by the cap later, and is read about 3 times at most, not N divided by the limit times.
SLICE_GROWTH_CAP = 10


def _parser(source: str, cfg: SiteConfig):
    if source == "origin":
        return origin.make_parser(cfg.request_id_header)
    if source == "cdn":
        if not cfg.cdn_field_map:
            raise ValueError("site has no cdn_field_map")
        return cdn.make_parser(cdn.load_field_map(cfg.cdn_field_map))
    raise ValueError(f"unknown source: {source}")


def _row(site_id: str, file: dict, line_no: int, p: ParsedLine, pair_state: str) -> tuple:
    source = file["source"]
    cdn = source == "cdn"
    return (
        site_id,
        p.ts,
        file["id"],
        line_no,
        source,
        p.method,
        p.host,
        p.path,
        p.status,
        p.status if cdn else None,
        None if cdn else p.status,
        p.bytes_sent,
        p.response_time_ms,
        p.referrer,
        p.client_ip,
        p.user_agent,
        client_key(p.user_agent, p.client_ip),
        p.request_id,
        p.edge_request_id,
        p.edge_signal or "none",
        line_key(p),
        pair_state,
        False,
    )


async def _import_file(
    conn: AsyncConnection,
    inbox: Inbox,
    cfg: SiteConfig,
    file: dict,
    now: datetime,
    max_lines: int,
) -> tuple[dict, bool]:
    # Reads at most max_lines lines in this run. Returns (counts of the whole file so far, done).
    # A file that is not done goes back to the queue with a resume offset (lines_done).
    site_id = cfg.site_id
    parse = _parser(file["source"], cfg)
    pair_state = "pending" if cfg.pairs_sources else "single"
    skip = file["lines_done"]
    if file["attempts"] > 1 and skip == 0:
        await events.delete_file_events(conn, site_id, file["id"])
    total = imported = rejected = 0
    rejects: list[tuple[int, str]] = []
    min_ts, max_ts = file["min_ts"], file["max_ts"]
    batch: list[tuple] = []
    latest = now + FUTURE_LIMIT
    done = True

    async def flush() -> None:
        nonlocal imported
        if batch:
            imported += await events.copy_events(conn, batch, imported_at=now)
            batch.clear()

    line_no = 0
    async for text in inbox.open_lines(file["object_key"]):
        line_no += 1
        if line_no <= skip:
            continue
        if total >= max_lines:
            done = False
            line_no -= 1
            break
        result = parse(text, line_no)
        if result is None:
            continue
        total += 1
        if isinstance(result, Reject):
            reject = result
        elif result.ts > latest:
            reject = Reject(line_no, "timestamp in the future")
        else:
            reject = None
        if reject is not None:
            rejected += 1
            if len(rejects) < import_files.MAX_REJECTS_PER_FILE:
                rejects.append((reject.line_no, reject.reason))
            continue
        min_ts = result.ts if min_ts is None else min(min_ts, result.ts)
        max_ts = result.ts if max_ts is None else max(max_ts, result.ts)
        batch.append(_row(site_id, file, line_no, result, pair_state))
        if len(batch) >= BATCH_ROWS:
            await flush()
    await flush()
    await import_files.add_rejects(conn, file["id"], rejects)
    counts = {
        "lines_total": file["lines_total"] + total,
        "lines_imported": file["lines_imported"] + imported,
        "lines_rejected": file["lines_rejected"] + rejected,
        "lines_duplicate": file["lines_duplicate"] + total - rejected - imported,
    }
    if done:
        await import_files.mark_success(conn, file["id"], counts, min_ts, max_ts)
    else:
        await import_files.save_progress(conn, file["id"], line_no, counts, min_ts, max_ts)
    run = {
        "lines_total": total,
        "lines_imported": imported,
        "lines_rejected": rejected,
        "lines_duplicate": total - rejected - imported,
    }
    return run, done


def _is_transient(exc: Exception) -> bool:
    # The inbox or the network is unavailable: the file is fine, so it is tried again later.
    if isinstance(exc, ObjectNotFound):
        return False
    if isinstance(exc, ClientError):
        return not is_missing(exc)
    return isinstance(exc, BotoCoreError | OSError | psycopg.errors.LockNotAvailable)


async def import_due_files(
    conn: AsyncConnection,
    site_id: str,
    inbox: Inbox | None = None,
    now: datetime | None = None,
) -> dict:
    settings = get_settings()
    cfg = load_site_config(site_id)
    inbox = inbox or get_inbox()
    now = now or datetime.now(UTC)
    totals = {
        "files": 0,
        "files_failed": 0,
        "lines_total": 0,
        "lines_imported": 0,
        "lines_rejected": 0,
        "lines_duplicate": 0,
    }
    bytes_done = 0
    # Partitions of today and tomorrow, before this step writes any row (no DDL lock held by us).
    today = now.astimezone(UTC).date()
    try:
        await events.ensure_partitions(conn, [today, today + timedelta(days=1)])
    except psycopg.Error as exc:
        # Not needed to start: copy_events makes a missing partition when a row needs it.
        log.warning("partition precreate failed", extra={"site_id": site_id, "error": repr(exc)})
    while (
        bytes_done < settings.work_limit_bytes and totals["lines_total"] < settings.work_limit_lines
    ):
        # claim_next_file takes live files first and backfill only when no live file waits (1.18)
        file = await import_files.claim_next_file(conn, site_id)
        if file is None:
            break
        bytes_done += file["size_bytes"]
        limit = settings.work_limit_lines
        allowance = min(max(limit, file["lines_done"]), limit * SLICE_GROWTH_CAP)
        budget = allowance - totals["lines_total"]
        try:
            async with conn.transaction():
                counts, done = await _import_file(conn, inbox, cfg, file, now, budget)
        except Exception as exc:
            if isinstance(exc, psycopg.Error) and not isinstance(exc, psycopg.errors.DataError):
                if not isinstance(exc, psycopg.errors.LockNotAvailable):
                    raise
            log.warning(
                "import failed",
                extra={"site_id": site_id, "file_id": str(file["id"]), "error": repr(exc)},
            )
            message = f"{type(exc).__name__}: {exc}"[:500]
            if _is_transient(exc):
                # Stop this step: the next claim would take the same file again at once.
                # A lock wait is not the file's fault: it does not count toward the retry limit.
                counted = not isinstance(exc, psycopg.errors.LockNotAvailable)
                failed = await import_files.release_file(
                    conn, file["id"], message, MAX_RETRIES, counted
                )
                totals["files_failed"] += int(failed)
                break
            await import_files.mark_failed(conn, file["id"], message)
            totals["files_failed"] += 1
            continue
        totals["files"] += int(done)
        for key, value in counts.items():
            totals[key] += value
    return totals


async def _file_chunks(path: Path, size: int) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        while chunk := await asyncio.to_thread(handle.read, size):
            yield chunk


async def import_local_file(
    path: Path,
    site_id: str,
    *,
    now: bool,
    force: bool,
    source: str | None = None,
    inbox: Inbox | None = None,
) -> dict:
    settings = get_settings()
    source = ingest.resolve_source(load_site_config(site_id), source)
    inbox = inbox or get_inbox()
    path = Path(path)
    key = f"cli/{site_id}/{uuid.uuid4().hex}-{path.name}"
    await inbox.ensure_bucket()
    sha256, size = await inbox.put_stream(key, _file_chunks(path, settings.ingest_chunk_bytes))
    result: dict = {"file_id": None, "duplicate": False, "reimport": False}
    async with db.connection() as conn:
        file_id = await import_files.insert_new(
            conn, site_id, source, key, sha256, size, "backfill", "cli"
        )
        if file_id is None:
            await inbox.delete(key)
            result["duplicate"] = True
            existing = await import_files.get_by_sha(conn, site_id, sha256)
            file_id = str(existing["id"])
            if force:
                if not await import_files.force_reimport(conn, file_id):
                    raise ValueError(
                        "cannot import again: the file is importing or the raw file was deleted"
                    )
                result["reimport"] = True
        result["file_id"] = file_id
    if now:
        async with db.connection() as conn:
            result["counts"] = await import_due_files(conn, site_id, inbox)
    return result
