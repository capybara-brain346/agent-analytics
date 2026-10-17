import ipaddress
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from src.config import get_settings

CGN = ipaddress.ip_network("100.64.0.0/10")

type IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


@dataclass(frozen=True)
class BotEntry:
    id: str
    vendor: str
    ua_pattern: str
    category: str
    verify: dict
    is_regex: bool = False


def _registry_dir() -> Path:
    return get_settings().config_dir / "registry"


def _stamp(path: Path) -> int:
    return path.stat().st_mtime_ns


@lru_cache
def _load_registry(path: str, stamp: int) -> tuple[str, tuple[BotEntry, ...]]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    entries = tuple(
        BotEntry(
            id=b["id"],
            vendor=b.get("vendor", ""),
            ua_pattern=b["ua_pattern"],
            category=b["category"],
            verify=b.get("verify") or {"method": "none"},
            is_regex=bool(b.get("regex", False)),
        )
        for b in raw.get("bots") or []
    )
    return str(raw.get("version", "0")), entries


def load_registry() -> tuple[str, list[BotEntry]]:
    path = _registry_dir() / "bots.yaml"
    version, entries = _load_registry(str(path), _stamp(path))
    return version, list(entries)


def match_user_agent(user_agent: str, entries: list[BotEntry] | None = None) -> BotEntry | None:
    if not user_agent:
        return None
    if entries is None:
        entries = load_registry()[1]
    for entry in sorted(entries, key=lambda e: len(e.ua_pattern), reverse=True):
        if entry.is_regex:
            if re.search(entry.ua_pattern, user_agent, re.IGNORECASE):
                return entry
        elif entry.ua_pattern.lower() in user_agent.lower():
            return entry
    return None


@lru_cache
def _load_shared(path: str, stamp: int) -> tuple[IPNetwork, ...]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return tuple(ipaddress.ip_network(r["cidr"]) for r in raw.get("ranges") or [])


def shared_ip_ranges() -> list[IPNetwork]:
    path = _registry_dir() / "shared-ip.yaml"
    extra = _load_shared(str(path), _stamp(path)) if path.is_file() else ()
    return [CGN, *extra]


def is_shared_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    return any(address.version == net.version and address in net for net in shared_ip_ranges())
