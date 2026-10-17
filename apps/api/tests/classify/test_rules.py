import pytest

from src.models.domain import UaType
from src.services.classify.rules import RULE_VERSION, classify

V, C, U, S, K = "VERIFIED", "CLAIMED", "UNVERIFIED", "SPOOFED", "UNKNOWN"
B, H, N = "bot", "human", "none"
BR, HL, LIB, BOT, OTH = (UaType.BROWSER, UaType.HEADLESS, UaType.LIBRARY, UaType.BOT, UaType.OTHER)

# verdict, category, ua, edge, class, confidence, rule_id
TABLE = [
    (S, "ai_crawler", BOT, N, 6, "low", "R1-spoofed"),
    (S, "search_crawler", BOT, B, 6, "medium", "R1-spoofed"),
    (V, "search_crawler", BOT, N, 1, "high", "R2-search-verified"),
    (C, "search_crawler", BOT, N, 3, "medium", "R3-search-unverified"),
    (U, "search_crawler", BOT, N, 3, "low", "R3-search-unverified"),
    (V, "ai_crawler", BOT, N, 2, "high", "R4-ai-agent"),
    (C, "ai_crawler", BOT, N, 2, "medium", "R4-ai-agent"),
    (U, "agent_client", BOT, N, 2, "low", "R4-ai-agent"),
    (V, "other_bot", BOT, N, 3, "high", "R5-other-bot"),
    (U, "other_bot", BOT, N, 3, "low", "R5-other-bot"),
    (U, "automation_tool", LIB, N, 3, "low", "R5-other-bot"),
    (K, None, LIB, N, 3, "low", "R5-library-ua"),
    (K, None, LIB, B, 3, "medium", "R5-library-ua"),
    (K, None, HL, N, 4, "low", "R6-automation"),
    (K, None, HL, B, 4, "medium", "R6-automation"),
    (K, None, HL, H, 4, "medium", "R6-automation"),
    (K, None, BR, B, 4, "medium", "R6-automation"),
    (K, None, BR, H, 5, "medium", "R7-browser-human"),
    (K, None, BR, N, 6, "low", "R8-unknown"),
    (K, None, OTH, N, 6, "low", "R8-unknown"),
    (K, None, OTH, H, 6, "medium", "R8-unknown"),
    (K, None, BOT, N, 3, "low", "R5-other-bot"),
]


@pytest.mark.parametrize(("verdict", "cat", "ua", "edge", "cls", "conf", "rule"), TABLE)
def test_rule_table(verdict, cat, ua, edge, cls, conf, rule):
    r = classify(verdict, cat, ua, edge)
    assert (r.traffic_class, r.confidence, r.rule_id) == (cls, conf, rule)
    assert r.evidence


def test_spoofed_flag_and_evidence():
    r = classify(S, "ai_crawler", BOT, N)
    assert r.flags == ["spoofed"]


def test_search_unverified_evidence():
    assert "unverified" in classify(C, "search_crawler", BOT, N).evidence


def test_browser_without_edge_evidence():
    assert classify(K, None, BR, N).evidence == "browser UA, not confirmed human"


def test_rule_version():
    assert RULE_VERSION
