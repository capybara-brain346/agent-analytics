import uuid
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from src.config import get_settings
from src.models.domain import FilePriority
from src.services.site_config import SiteConfig, load_site_config, token_matches
from src.store import db, import_files
from src.store.inbox import GZIP_MAGIC, Inbox

MINUTE = 60.0
DAY = 86_400.0


class PayloadTooLarge(Exception):
    pass


class EmptyBody(Exception):
    pass


@dataclass
class _Window:
    requests: deque[float]
    bytes: deque[tuple[float, int]]
    bytes_total: int = 0


# In-process sliding windows (decision 1.16). One API process = one limiter.
_windows: dict[str, _Window] = {}


def reset_limits() -> None:
    _windows.clear()


def _window(site_id: str) -> _Window:
    return _windows.setdefault(site_id, _Window(deque(), deque()))


def _trim(w: _Window, now: float) -> None:
    while w.requests and now - w.requests[0] >= MINUTE:
        w.requests.popleft()
    while w.bytes and now - w.bytes[0][0] >= DAY:
        w.bytes_total -= w.bytes.popleft()[1]


async def check_site_token(site_id: str, token: str) -> bool:
    return token_matches(load_site_config(site_id), token)


async def check_rate_limit(
    site_id: str, size_hint: int | None = None, now: float | None = None
) -> bool:
    # True = allowed. An allowed call counts as one request.
    settings = get_settings()
    now = monotonic() if now is None else now
    w = _window(site_id)
    _trim(w, now)
    if len(w.requests) >= settings.ingest_rate_per_minute:
        return False
    if w.bytes_total + (size_hint or 0) > settings.ingest_bytes_per_day:
        return False
    w.requests.append(now)
    return True


def record_bytes(site_id: str, size: int, now: float | None = None) -> None:
    w = _window(site_id)
    now = monotonic() if now is None else now
    w.bytes.append((now, size))
    w.bytes_total += size


def resolve_source(config: SiteConfig, source: str | None) -> str:
    # ValueError text = reason for a 422.
    names = [str(s) for s in config.sources]
    if source is None:
        if len(names) == 1:
            return names[0]
        raise ValueError("source is required: this site has " + " and ".join(names))
    if source not in names:
        raise ValueError(f"source must be one of: {', '.join(names)}")
    return source


async def _limited(first: bytes, rest: AsyncIterator[bytes], limit: int) -> AsyncIterator[bytes]:
    total = len(first)
    if total > limit:
        raise PayloadTooLarge(limit)
    yield first
    async for chunk in rest:
        if not chunk:
            continue
        total += len(chunk)
        if total > limit:
            raise PayloadTooLarge(limit)
        yield chunk


def object_key(site_id: str, source: str, gzipped: bool, now: datetime | None = None) -> str:
    day = (now or datetime.now(UTC)).strftime("%Y-%m-%d")
    return f"{site_id}/{source}/{day}/{uuid.uuid4().hex}{'.gz' if gzipped else '.log'}"


async def accept_chunk(
    site_id: str,
    source: str,
    body: AsyncIterator[bytes],
    priority: FilePriority | str,
    entry: str,
    inbox: Inbox,
    max_bytes: int,
) -> tuple[str, bool]:
    # Returns (file_id, duplicate). No parsing here (1.15).
    rest = aiter(body)
    first = b""
    async for chunk in rest:
        if chunk:
            first = chunk
            break
    if not first:
        raise EmptyBody
    key = object_key(site_id, source, first[:2] == GZIP_MAGIC)
    try:
        sha256, size = await inbox.put_stream(key, _limited(first, rest, max_bytes))
    except BaseException:
        await inbox.delete(key)
        raise
    try:
        async with db.connection() as conn:
            file_id = await import_files.insert_new(
                conn, site_id, source, key, sha256, size, priority, entry
            )
            existing = None
            if file_id is None:
                existing = await import_files.get_by_sha(conn, site_id, sha256)
    except BaseException:
        await inbox.delete(key)
        raise
    if file_id is None:
        await inbox.delete(key)
        return (str(existing["id"]) if existing else "", True)
    record_bytes(site_id, size)
    return file_id, False
