import hashlib
import ipaddress
import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from psycopg import AsyncConnection

from src.config import get_settings
from src.logger import get_logger
from src.services import registry
from src.store import db
from src.store import ip_lists as store

log = get_logger(__name__)

type Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_prefixes(payload: object) -> list[str]:
    # Google style {"prefixes": [{"ipv4Prefix": ..}, {"ipv6Prefix": ..}]} or a plain list of CIDRs.
    if isinstance(payload, dict):
        items = payload.get("prefixes")
    else:
        items = payload
    if not isinstance(items, list):
        raise ValueError("unknown IP list format")
    found: set[Network] = set()
    for item in items:
        if isinstance(item, dict):
            item = item.get("ipv4Prefix") or item.get("ipv6Prefix") or item.get("cidr")
        if not isinstance(item, str):
            continue
        try:
            found.add(ipaddress.ip_network(item.strip(), strict=False))
        except ValueError:
            continue
    if not found:
        raise ValueError("IP list has no prefixes")
    return [
        str(n) for n in sorted(found, key=lambda n: (n.version, n.network_address, n.prefixlen))
    ]


def ip_in_snapshot(ip: str, prefixes) -> bool:
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    for prefix in prefixes:
        net = prefix if not isinstance(prefix, str) else ipaddress.ip_network(prefix, strict=False)
        if net.version == address.version and address in net:
            return True
    return False


async def latest_snapshot(conn: AsyncConnection, source: str) -> dict | None:
    return await store.latest_snapshot(conn, source)


def _snapshot_date(payload: object, fallback: date) -> date:
    stamp = payload.get("creationTime") if isinstance(payload, dict) else None
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    return fallback


def _bundled(source: str) -> tuple[object, date] | None:
    path: Path = get_settings().ip_list_dir / source
    if not path.is_file():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC).date()
    payload = json.loads(path.read_text())
    return payload, _snapshot_date(payload, mtime)


async def _store_if_changed(conn: AsyncConnection, source: str, payload: object, day: date) -> bool:
    prefixes = parse_prefixes(payload)
    current = await store.latest_snapshot(conn, source)
    if current is not None and sorted(map(str, current["prefixes"])) == sorted(prefixes):
        return False
    version = day.isoformat()
    if await store.save_snapshot(conn, source, version, prefixes):
        return True
    # Same day, new content: keep the date, add a short content hash.
    digest = hashlib.sha256("\n".join(prefixes).encode()).hexdigest()[:6]
    return await store.save_snapshot(conn, source, f"{version}-{digest}", prefixes)


async def _run(conn: AsyncConnection, client: httpx.AsyncClient | None) -> dict:
    settings = get_settings()
    counts = {"sources": 0, "new": 0, "unchanged": 0, "failed": 0}
    sources: dict[str, str | None] = {}
    for entry in registry.load_registry()[1]:
        verify = entry.verify
        if verify.get("method") == "ip_list" and verify.get("source"):
            sources.setdefault(verify["source"], verify.get("url"))
    owned = None
    if client is None and not settings.offline:
        client = owned = httpx.AsyncClient(timeout=30, follow_redirects=True)
    try:
        for source, url in sources.items():
            counts["sources"] += 1
            try:
                payload, day = None, datetime.now(UTC).date()
                if settings.offline or not url:
                    loaded = _bundled(source)
                    if loaded is None:
                        raise FileNotFoundError(f"no bundled file for {source}")
                    payload, day = loaded
                else:
                    try:
                        response = await client.get(url)
                        response.raise_for_status()
                        payload = response.json()
                        day = _snapshot_date(payload, day)
                    except Exception:
                        # Download failed: use the bundled file only when no snapshot exists yet.
                        if await store.latest_snapshot(conn, source) is not None:
                            raise
                        loaded = _bundled(source)
                        if loaded is None:
                            raise
                        payload, day = loaded
                created = await _store_if_changed(conn, source, payload, day)
                counts["new" if created else "unchanged"] += 1
            except Exception as exc:
                counts["failed"] += 1
                log.warning("ip list %s not updated: %s", source, exc)
    finally:
        if owned is not None:
            await owned.aclose()
    return counts


async def download_snapshots(
    conn: AsyncConnection | None = None, client: httpx.AsyncClient | None = None
) -> dict:
    if conn is not None:
        return await _run(conn, client)
    async with db.connection() as own:
        return await _run(own, client)
