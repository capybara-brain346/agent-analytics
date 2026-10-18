import asyncio
import ipaddress
from datetime import UTC, datetime, timedelta
from typing import Protocol

import dns.asyncresolver
import dns.exception
import dns.resolver
import dns.reversename
from psycopg import AsyncConnection

from src.config import get_settings
from src.services import registry
from src.services.classify import rules as classify_rules
from src.services.verify.ip_lists import ip_in_snapshot
from src.store import ip_lists as ip_store
from src.store import verdicts as store

DNS_CONCURRENCY = 20


class Resolver(Protocol):
    async def ptr(self, ip: str) -> list[str]: ...

    async def addresses(self, host: str) -> list[str]: ...


class DnsResolver:
    def __init__(self, timeout: float):
        self._resolver = dns.asyncresolver.Resolver()
        self._resolver.timeout = timeout
        self._resolver.lifetime = timeout

    async def _query(self, name, rdtype: str) -> list:
        try:
            answer = await self._resolver.resolve(name, rdtype)
        except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer:
            return []
        return list(answer)

    async def ptr(self, ip: str) -> list[str]:
        records = await self._query(dns.reversename.from_address(ip), "PTR")
        return [str(r.target).rstrip(".") for r in records]

    async def addresses(self, host: str) -> list[str]:
        found = []
        for rdtype in ("A", "AAAA"):
            found += [r.address for r in await self._query(host, rdtype)]
        return found


def _same_ip(a: str, b: str) -> bool:
    try:
        return ipaddress.ip_address(a) == ipaddress.ip_address(b)
    except ValueError:
        return False


def _has_suffix(host: str, suffixes: list[str]) -> bool:
    host = host.lower().rstrip(".")
    return any(host == s.lower() or host.endswith("." + s.lower()) for s in suffixes)


async def reverse_dns_check(ip: str, suffixes: list[str], resolver: Resolver) -> tuple[str, str]:
    # Returns (verdict, evidence). A DNS error or timeout raises: the caller maps it to UNVERIFIED.
    hosts = await resolver.ptr(ip)
    if not hosts:
        return "SPOOFED", f"{ip} has no reverse DNS name"
    for host in hosts:
        if not _has_suffix(host, suffixes):
            continue
        if any(_same_ip(ip, a) for a in await resolver.addresses(host)):
            return "VERIFIED", f"{ip} -> {host}, forward lookup matches"
        return "SPOOFED", f"{ip} -> {host}, forward lookup does not return {ip}"
    return "SPOOFED", f"{ip} -> {', '.join(hosts)}, not in {', '.join(suffixes)}"


def _result(verdict: str, method: str, evidence: str, snapshot: str | None = None) -> dict:
    return {
        "verdict": verdict,
        "method": method,
        "evidence": evidence,
        "ip_snapshot_version": snapshot,
    }


async def _check(
    entry: registry.BotEntry | None,
    ip: str,
    snapshots: dict,
    resolver: Resolver,
    semaphore: asyncio.Semaphore,
    timeout: float,
) -> dict:
    if entry is None:
        return _result("UNKNOWN", "none", "no bot name in UA")
    method = entry.verify.get("method", "none")
    if method == "ip_list":
        snap = snapshots.get(entry.verify.get("source"))
        if snap is None:
            return _result("UNVERIFIED", "ip_list", "no IP list snapshot")
        day = f"snapshot {snap['version']}"
        if ip_in_snapshot(ip, snap["networks"]):
            return _result("VERIFIED", "ip_list", f"in vendor list, {day}", snap["version"])
        return _result("SPOOFED", "ip_list", f"{ip} not in vendor list, {day}", snap["version"])
    if method == "rdns":
        try:
            async with semaphore:
                verdict, evidence = await asyncio.wait_for(
                    reverse_dns_check(ip, entry.verify.get("suffixes") or [], resolver),
                    timeout * 2,
                )
        except Exception as exc:
            return _result("UNVERIFIED", "rdns", f"DNS lookup failed: {type(exc).__name__}")
        return _result(verdict, "rdns", evidence)
    return _result("CLAIMED", "none", f"{entry.vendor} publishes no verification method")


def _reusable(
    current: dict | None,
    registry_version: str,
    entry: registry.BotEntry | None,
    snapshot_version: str | None,
    rdns_cutoff: datetime,
    retry_cutoff: datetime,
) -> bool:
    if current is None or current["registry_version"] != registry_version:
        return False
    # A new classify rule version needs new rows, so classify can fill them (None = not set yet).
    if current["rule_version"] not in (None, classify_rules.RULE_VERSION):
        return False
    # A DNS error or timeout is not a final answer: retry it soon, not after the full TTL.
    if (
        current["method"] == "rdns"
        and current["verdict"] == "UNVERIFIED"
        and current["checked_at"] < retry_cutoff
    ):
        return False
    method = entry.verify.get("method", "none") if entry else "none"
    if method == "ip_list" and current["ip_snapshot_version"] != snapshot_version:
        return False
    if current["method"] == "rdns" and current["checked_at"] < rdns_cutoff:
        return False
    return True


async def verify_new_clients(
    conn: AsyncConnection,
    site_id: str,
    now: datetime | None = None,
    resolver: Resolver | None = None,
) -> dict:
    settings = get_settings()
    now = now or datetime.now(UTC)
    resolver = resolver or DnsResolver(settings.dns_timeout_seconds)
    counts = {"groups": 0, "events": 0, "reused": 0, "new_rows": 0, "checks": 0}

    groups = await store.pending_client_groups(conn, site_id)
    counts["groups"] = len(groups)
    if not groups:
        return counts

    registry_version, entries = registry.load_registry()
    versions = await ip_store.latest_versions(conn)
    snapshots: dict[str, dict] = {}
    for source in versions:
        snap = await ip_store.latest_snapshot(conn, source)
        snapshots[source] = {"version": snap["version"], "networks": list(snap["prefixes"])}
    rdns_cutoff = now - timedelta(hours=settings.rdns_ttl_hours)
    retry_cutoff = now - timedelta(minutes=settings.unverified_retry_minutes)

    todo = []
    for g in groups:
        entry = registry.match_user_agent(g["user_agent"] or "", entries)
        source = entry.verify.get("source") if entry else None
        current = await store.current_verdict(conn, site_id, g["client_key"], g["edge_signal"])
        if _reusable(
            current, registry_version, entry, versions.get(source), rdns_cutoff, retry_cutoff
        ):
            counts["reused"] += 1
            await _assign(conn, site_id, g, current["id"], counts)
        else:
            todo.append((g, entry))

    # One check for each client_key; edge_signal only splits the rows.
    semaphore = asyncio.Semaphore(DNS_CONCURRENCY)
    unique = {}
    for g, entry in todo:
        unique.setdefault(g["client_key"], (entry, g["client_ip"]))
    results = await asyncio.gather(
        *(
            _check(entry, ip, snapshots, resolver, semaphore, settings.dns_timeout_seconds)
            for entry, ip in unique.values()
        )
    )
    by_key = dict(zip(unique, results, strict=True))
    counts["checks"] = len(unique)

    for g, entry in todo:
        result = by_key[g["client_key"]]
        verdict_id = await store.append_verdict(
            conn,
            {
                "site_id": site_id,
                "client_key": g["client_key"],
                "edge_signal": g["edge_signal"],
                "user_agent": g["user_agent"],
                "client_ip": g["client_ip"],
                "claimed_agent": entry.id if entry else None,
                "registry_category": entry.category if entry else None,
                "registry_version": registry_version,
                "rule_version": classify_rules.RULE_VERSION,
                "checked_at": now,
                "flags": ["spoofed"] if result["verdict"] == "SPOOFED" else [],
            }
            | result,
        )
        counts["new_rows"] += 1
        await _assign(conn, site_id, g, verdict_id, counts)
    return counts


async def _assign(
    conn: AsyncConnection, site_id: str, group: dict, verdict_id: int, counts: dict
) -> None:
    counts["events"] += await store.assign_events_verdict(
        conn,
        site_id,
        group["client_key"],
        group["edge_signal"],
        verdict_id,
        group["min_ts"],
        group["max_ts"],
    )
