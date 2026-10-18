import json

import httpx
import pytest

from src.config import get_settings
from src.services import verify
from src.store import ip_lists as store

GOOGLE = {
    "creationTime": "2026-10-11T00:00:00",
    "prefixes": [{"ipv4Prefix": "20.171.0.0/16"}, {"ipv6Prefix": "2001:db8::/32"}],
}


def client_for(payloads: dict[str, object], fail: set[str] = frozenset()):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host in fail:
            return httpx.Response(500)
        return httpx.Response(200, json=payloads.get(str(request.url), GOOGLE))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def snapshots(conn):
    cur = await conn.execute("select source, version from ip_list_snapshots order by 1, 2")
    return await cur.fetchall()


def test_parse_formats():
    assert verify.parse_prefixes(GOOGLE) == ["20.171.0.0/16", "2001:db8::/32"]
    assert verify.parse_prefixes(["1.2.3.0/24", "1.2.3.4"]) == ["1.2.3.0/24", "1.2.3.4/32"]
    with pytest.raises(ValueError):
        verify.parse_prefixes({"nothing": 1})


def test_ip_in_snapshot():
    prefixes = ["20.171.0.0/16", "2001:db8::/32"]
    assert verify.ip_in_snapshot("20.171.1.5", prefixes)
    assert verify.ip_in_snapshot("2001:db8::1", prefixes)
    assert not verify.ip_in_snapshot("20.172.0.1", prefixes)
    assert not verify.ip_in_snapshot("not-an-ip", prefixes)


async def test_download_stores_once_and_versions_on_change(conn, settings):
    async with client_for({}) as http:
        first = await verify.download_snapshots(conn, http)
        second = await verify.download_snapshots(conn, http)
    assert first["new"] >= 3 and first["failed"] == 0
    assert second["new"] == 0 and second["unchanged"] == first["new"]
    snap = await verify.latest_snapshot(conn, "openai-gptbot.json")
    assert snap["version"] == "2026-10-11"
    assert verify.ip_in_snapshot("20.171.1.5", snap["prefixes"])
    changed = dict(GOOGLE, prefixes=[{"ipv4Prefix": "9.9.9.0/24"}])
    async with client_for({"https://openai.com/gptbot.json": changed}) as http:
        await verify.download_snapshots(conn, http)
    rows = [r for r in await snapshots(conn) if r[0] == "openai-gptbot.json"]
    assert len(rows) == 2 and rows[0][1] == "2026-10-11"
    assert (await store.latest_versions(conn))["openai-gptbot.json"] == rows[1][1]


async def test_download_failure_keeps_old_snapshot(conn, settings):
    await store.save_snapshot(conn, "openai-gptbot.json", "2026-01-01", ["1.1.1.0/24"])
    async with client_for({}, fail={"openai.com"}) as http:
        counts = await verify.download_snapshots(conn, http)
    assert counts["failed"] == 1
    assert (await store.latest_versions(conn))["openai-gptbot.json"] == "2026-01-01"


async def test_download_failure_falls_back_to_bundled(conn, settings):
    async with client_for({}, fail={"openai.com"}) as http:
        await verify.download_snapshots(conn, http)
    snap = await verify.latest_snapshot(conn, "openai-gptbot.json")
    assert verify.ip_in_snapshot("20.171.1.5", snap["prefixes"])


async def test_offline_loads_bundled_without_network(conn, monkeypatch):
    monkeypatch.setenv("OFFLINE", "true")
    get_settings.cache_clear()

    def boom(request):
        raise AssertionError("network used")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as http:
        counts = await verify.download_snapshots(conn, http)
    assert counts["new"] >= 3
    snap = await verify.latest_snapshot(conn, "openai-gptbot.json")
    assert snap["version"] == "2026-10-10"
    assert verify.ip_in_snapshot("20.171.1.5", snap["prefixes"])
    again = await verify.download_snapshots(conn)
    assert again["new"] == 0


async def test_offline_custom_dir(conn, monkeypatch, tmp_path):
    (tmp_path / "openai-gptbot.json").write_text(json.dumps(["5.5.5.0/24"]))
    monkeypatch.setenv("OFFLINE", "true")
    monkeypatch.setenv("IP_LIST_DIR", str(tmp_path))
    get_settings.cache_clear()
    counts = await verify.download_snapshots(conn)
    assert counts["new"] == 1 and counts["failed"] >= 1
    assert await store.ip_in_prefixes(
        conn,
        "openai-gptbot.json",
        (await store.latest_versions(conn))["openai-gptbot.json"],
        "5.5.5.9",
    )
