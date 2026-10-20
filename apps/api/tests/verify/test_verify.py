import asyncio
from datetime import timedelta

import pytest

from src.services import verify
from tests.factories import (
    CHROME_UA,
    NOW,
    make_event,
    make_ip_list_snapshot,
)

GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
MISTRAL_UA = "MistralAI-User/1.0"
CLAUDE_UA = "ClaudeBot/1.0"
CLAUDE_USER_UA = "Claude-User/1.0"


class FakeResolver:
    def __init__(self, ptr=None, forward=None, error=None, delay=0.0):
        self.ptr_map = ptr or {}
        self.forward = forward or {}
        self.error = error
        self.delay = delay
        self.calls = 0
        self.active = 0
        self.peak = 0

    async def ptr(self, ip):
        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.error:
                raise self.error
            return self.ptr_map.get(ip, [])
        finally:
            self.active -= 1

    async def addresses(self, host):
        return self.forward.get(host, [])


async def rows(conn, sql="select * from verdicts order by id"):
    cur = await conn.execute(sql)
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in await cur.fetchall()]


async def verdict_ids(conn):
    return [r["verdict_id"] for r in await rows(conn, "select verdict_id from events order by id")]


async def test_ip_list_verified(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn)
    counts = await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    [v] = await rows(conn)
    assert v["verdict"] == "VERIFIED" and v["method"] == "ip_list"
    assert v["claimed_agent"] == "gptbot" and v["registry_category"] == "ai_crawler"
    assert v["ip_snapshot_version"] == "2026-10-10" and "2026-10-10" in v["evidence"]
    assert v["registry_version"] == "1" and v["checked_at"] == NOW and v["flags"] == []
    assert v["traffic_class"] is None
    assert await verdict_ids(conn) == [v["id"]]
    assert counts["new_rows"] == 1 and counts["events"] == 1


async def test_ip_list_spoofed(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn, client_ip="45.33.9.9")
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    [v] = await rows(conn)
    assert v["verdict"] == "SPOOFED" and v["flags"] == ["spoofed"]
    assert "2026-10-10" in v["evidence"]


async def test_no_snapshot_unverified(conn):
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    [v] = await rows(conn)
    assert v["verdict"] == "UNVERIFIED" and v["evidence"] == "no IP list snapshot"
    assert v["ip_snapshot_version"] is None


async def test_unknown_and_claimed(conn):
    await make_event(conn, user_agent=CHROME_UA, client_ip="81.2.3.4")
    await make_event(conn, user_agent=MISTRAL_UA, client_ip="160.79.1.1")
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    by_ua = {r["user_agent"]: r for r in await rows(conn)}
    assert by_ua[CHROME_UA]["verdict"] == "UNKNOWN" and by_ua[CHROME_UA]["method"] == "none"
    assert by_ua[CHROME_UA]["claimed_agent"] is None
    assert by_ua[MISTRAL_UA]["verdict"] == "CLAIMED" and by_ua[MISTRAL_UA]["method"] == "none"


async def test_anthropic_bots_share_one_ip_list(conn):
    await make_ip_list_snapshot(conn, source="anthropic.json", prefixes=["160.79.104.0/23"])
    await make_event(conn, user_agent=CLAUDE_UA, client_ip="160.79.104.10")
    await make_event(conn, user_agent=CLAUDE_USER_UA, client_ip="104.16.1.1")
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    by_ua = {r["user_agent"]: r for r in await rows(conn)}
    assert by_ua[CLAUDE_UA]["verdict"] == "VERIFIED" and by_ua[CLAUDE_UA]["method"] == "ip_list"
    assert by_ua[CLAUDE_USER_UA]["verdict"] == "SPOOFED"
    assert by_ua[CLAUDE_USER_UA]["claimed_agent"] == "claude-user"


GOOD = FakeResolver(
    ptr={"66.249.66.1": ["crawl-66-249-66-1.googlebot.com"]},
    forward={"crawl-66-249-66-1.googlebot.com": ["66.249.66.1"]},
)


async def test_rdns_verified(conn):
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW, GOOD)
    [v] = await rows(conn)
    assert v["verdict"] == "VERIFIED" and v["method"] == "rdns"
    assert "googlebot.com" in v["evidence"]


@pytest.mark.parametrize(
    "resolver",
    [
        FakeResolver(ptr={"45.33.9.9": ["host.linode.com"]}),
        FakeResolver(
            ptr={"45.33.9.9": ["crawl.googlebot.com"]}, forward={"crawl.googlebot.com": ["1.1.1.1"]}
        ),
        FakeResolver(ptr={"45.33.9.9": ["evilgooglebot.com"]}),
        FakeResolver(),
    ],
)
async def test_rdns_spoofed(conn, resolver):
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="45.33.9.9")
    await verify.verify_new_clients(conn, "example", NOW, resolver)
    [v] = await rows(conn)
    assert v["verdict"] == "SPOOFED" and v["flags"] == ["spoofed"]


async def test_rdns_error_is_unverified(conn):
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver(error=TimeoutError()))
    [v] = await rows(conn)
    assert v["verdict"] == "UNVERIFIED" and v["method"] == "rdns" and v["flags"] == []


async def test_rdns_slow_resolver_times_out(conn, monkeypatch):
    from src.config import get_settings

    monkeypatch.setenv("DNS_TIMEOUT_SECONDS", "0.05")
    get_settings.cache_clear()
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver(delay=5))
    [v] = await rows(conn)
    assert v["verdict"] == "UNVERIFIED"


async def test_dns_concurrency_bounded(conn):
    for i in range(45):
        await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip=f"45.33.9.{i + 1}")
    resolver = FakeResolver(delay=0.01)
    await verify.verify_new_clients(conn, "example", NOW, resolver)
    assert resolver.calls == 45 and resolver.peak <= 20


async def test_reuse_without_new_row(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    await make_event(conn)
    counts = await verify.verify_new_clients(
        conn, "example", NOW + timedelta(hours=1), FakeResolver()
    )
    assert len(await rows(conn)) == 1
    assert counts["reused"] == 1 and counts["new_rows"] == 0 and counts["events"] == 1
    assert len(set(await verdict_ids(conn))) == 1 and None not in await verdict_ids(conn)


async def test_new_row_on_snapshot_change_old_events_keep_id(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    await make_ip_list_snapshot(
        conn, version="2026-10-11", fetched_at=NOW + timedelta(days=1), prefixes=["9.9.9.0/24"]
    )
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW + timedelta(days=1), FakeResolver())
    vs = await rows(conn)
    assert [v["verdict"] for v in vs] == ["VERIFIED", "SPOOFED"]
    assert vs[1]["ip_snapshot_version"] == "2026-10-11"
    assert await verdict_ids(conn) == [vs[0]["id"], vs[1]["id"]]


async def test_snapshot_of_other_source_does_not_trigger(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    await make_ip_list_snapshot(conn, source="ccbot.json", version="2026-10-12")
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    assert len(await rows(conn)) == 1


async def test_new_row_after_registry_version_change(conn, config_dir):
    await make_ip_list_snapshot(conn)
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    path = config_dir / "registry" / "bots.yaml"
    path.write_text(path.read_text().replace('version: "1"', 'version: "2"', 1))
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    vs = await rows(conn)
    assert [v["registry_version"] for v in vs] == ["1", "2"]


async def test_rdns_ttl(conn):
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW, GOOD)
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW + timedelta(hours=23), GOOD)
    assert len(await rows(conn)) == 1
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW + timedelta(hours=25), GOOD)
    vs = await rows(conn)
    assert len(vs) == 2 and vs[1]["checked_at"] == NOW + timedelta(hours=25)
    assert (await verdict_ids(conn))[0] == vs[0]["id"]


async def test_edge_signal_split_one_check(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn, edge_signal="bot")
    await make_event(conn, edge_signal="human")
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1", edge_signal="bot")
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1", edge_signal="none")
    resolver = FakeResolver(
        ptr={"66.249.66.1": ["a.googlebot.com"]}, forward={"a.googlebot.com": ["66.249.66.1"]}
    )
    counts = await verify.verify_new_clients(conn, "example", NOW, resolver)
    assert len(await rows(conn)) == 4 and counts["checks"] == 2 and resolver.calls == 1
    ids = await verdict_ids(conn)
    assert len(set(ids)) == 4


async def test_pending_and_ungrouped_ignored(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn, pair_state="pending")
    await make_event(conn, client_key=None)
    counts = await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    assert await rows(conn) == [] and counts["groups"] == 0
    assert await verdict_ids(conn) == [None, None]


async def test_other_site_untouched(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn, site_id="other")
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    assert await rows(conn) == [] and await verdict_ids(conn) == [None]


async def test_idempotent(conn):
    await make_ip_list_snapshot(conn)
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    counts = await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    assert counts["groups"] == 0 and len(await rows(conn)) == 1


async def test_new_row_after_classify_rule_version_change(conn, monkeypatch):
    from src.services import classify
    from src.services.classify import rules

    await make_ip_list_snapshot(conn)
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    await classify.classify_new_verdicts(conn, "example")
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    assert len(await rows(conn)) == 1
    monkeypatch.setattr(rules, "RULE_VERSION", "2")
    monkeypatch.setattr("src.services.classify.service.RULE_VERSION", "2")
    await make_event(conn)
    await verify.verify_new_clients(conn, "example", NOW, FakeResolver())
    vs = await rows(conn)
    assert len(vs) == 2 and vs[1]["rule_version"] == "2" and vs[1]["traffic_class"] is None
    await classify.classify_new_verdicts(conn, "example")
    assert [v["rule_version"] for v in await rows(conn)] == ["1", "2"]
    assert (await verdict_ids(conn))[-1] == vs[1]["id"]


async def test_unverified_dns_error_is_retried_after_an_hour(conn):
    broken = FakeResolver(error=TimeoutError())
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW, broken)
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW + timedelta(minutes=59), GOOD)
    assert len(await rows(conn)) == 1
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW + timedelta(minutes=61), GOOD)
    vs = await rows(conn)
    assert [v["verdict"] for v in vs] == ["UNVERIFIED", "VERIFIED"]


async def test_verified_rdns_is_not_retried_early(conn):
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW, GOOD)
    await make_event(conn, user_agent=GOOGLEBOT_UA, client_ip="66.249.66.1")
    await verify.verify_new_clients(conn, "example", NOW + timedelta(minutes=90), GOOD)
    assert len(await rows(conn)) == 1
