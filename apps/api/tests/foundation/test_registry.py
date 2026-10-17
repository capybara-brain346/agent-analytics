from pathlib import Path

import pytest
import yaml

from src.models.domain import RegistryCategory
from src.services import registry


def test_load_registry_default_file() -> None:
    version, entries = registry.load_registry()
    assert version
    assert len(entries) >= 20
    assert len({e.id for e in entries}) == len(entries)
    for entry in entries:
        assert entry.category in set(RegistryCategory)
        assert entry.verify["method"] in {"ip_list", "rdns", "none"}
        if entry.verify["method"] == "ip_list":
            assert entry.verify["source"]
        if entry.verify["method"] == "rdns":
            assert entry.verify["suffixes"]


@pytest.mark.parametrize(
    ("ua", "bot_id"),
    [
        (
            "Mozilla/5.0 AppleWebKit/537.36; compatible; GPTBot/1.2; +https://openai.com/gptbot",
            "gptbot",
        ),
        ("Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)", "chatgpt-user"),
        (
            "Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
            "oai-searchbot",
        ),
        ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "claudebot"),
        ("Claude-User/1.0", "claude-user"),
        ("Mozilla/5.0 (compatible; PerplexityBot/1.0)", "perplexitybot"),
        ("Mozilla/5.0 (compatible; Perplexity-User/1.0)", "perplexity-user"),
        ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "googlebot"),
        ("Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", "bingbot"),
        ("python-requests/2.32.3", "python-requests"),
        ("curl/8.5.0", "curl"),
    ],
)
def test_match_known_user_agents(ua: str, bot_id: str) -> None:
    _, entries = registry.load_registry()
    match = registry.match_user_agent(ua, entries)
    assert match is not None
    assert match.id == bot_id


def test_match_is_case_insensitive() -> None:
    _, entries = registry.load_registry()
    assert registry.match_user_agent("gptbot/1.2", entries).id == "gptbot"


def test_browser_ua_has_no_match() -> None:
    _, entries = registry.load_registry()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36"
    assert registry.match_user_agent(ua, entries) is None
    assert registry.match_user_agent("", entries) is None


def entry(id: str, pattern: str, regex: bool = False) -> registry.BotEntry:
    return registry.BotEntry(
        id=id,
        vendor="v",
        ua_pattern=pattern,
        category="other_bot",
        verify={"method": "none"},
        is_regex=regex,
    )


def test_longest_pattern_wins_over_order() -> None:
    entries = [entry("short", "Bot"), entry("long", "ChatGPT-User")]
    assert registry.match_user_agent("x ChatGPT-User/1.0 Bot", entries).id == "long"


def test_regex_pattern() -> None:
    entries = [entry("rx", r"^Foo/\d+$", regex=True)]
    assert registry.match_user_agent("foo/12", entries).id == "rx"
    assert registry.match_user_agent("foo/x", entries) is None


def test_custom_registry_dir(config_dir: Path) -> None:
    root = config_dir
    (root / "registry" / "bots.yaml").write_text(
        yaml.safe_dump(
            {
                "version": "9",
                "bots": [
                    {
                        "id": "x",
                        "vendor": "X",
                        "ua_pattern": "XBot",
                        "category": "ai_crawler",
                        "verify": {"method": "none"},
                    }
                ],
            }
        )
    )
    version, entries = registry.load_registry()
    assert version == "9"
    assert [e.id for e in entries] == ["x"]


def test_shared_ip_ranges_include_cgn() -> None:
    nets = registry.shared_ip_ranges()
    assert any(str(n) == "100.64.0.0/10" for n in nets)


@pytest.mark.parametrize(
    ("ip", "shared"),
    [
        ("100.64.0.1", True),
        ("100.127.255.254", True),
        ("100.128.0.1", False),
        ("20.171.1.5", False),
        ("104.16.1.1", True),
        ("not-an-ip", False),
        ("2001:db8::1", False),
    ],
)
def test_is_shared_ip(ip: str, shared: bool) -> None:
    assert registry.is_shared_ip(ip) is shared


def test_ip_list_entries_have_https_url_and_json_source(settings):
    _, entries = registry.load_registry()
    lists = [e for e in entries if e.verify.get("method") == "ip_list"]
    assert lists
    for e in lists:
        assert e.verify["url"].startswith("https://"), e.id
        assert e.verify["source"].endswith(".json"), e.id
    assert not any(e.id == "amazonbot" for e in lists)
