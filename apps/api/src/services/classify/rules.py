from dataclasses import dataclass, field

from src.models.domain import (
    Confidence,
    EdgeSignal,
    RegistryCategory,
    TrafficClass,
    UaType,
    Verdict,
)

RULE_VERSION = "1"


@dataclass(frozen=True)
class Classification:
    traffic_class: int
    confidence: str
    rule_id: str
    evidence: str
    flags: list[str] = field(default_factory=list)


def _confidence(verdict: str, edge_signal: str) -> str:
    if verdict == Verdict.VERIFIED:
        return Confidence.HIGH
    if verdict == Verdict.CLAIMED or edge_signal in (EdgeSignal.BOT, EdgeSignal.HUMAN):
        return Confidence.MEDIUM
    return Confidence.LOW


def classify(
    verdict: str, registry_category: str | None, ua_type: str, edge_signal: str
) -> Classification:
    conf = _confidence(verdict, edge_signal)

    def out(cls: TrafficClass, rule_id: str, evidence: str, flags: list[str] | None = None):
        return Classification(int(cls), str(conf), rule_id, evidence, flags or [])

    if verdict == Verdict.SPOOFED:
        return out(
            TrafficClass.UNKNOWN,
            "R1-spoofed",
            "claims a known bot, failed verification (spoofed)",
            ["spoofed"],
        )
    if registry_category == RegistryCategory.SEARCH_CRAWLER:
        if verdict == Verdict.VERIFIED:
            return out(
                TrafficClass.VERIFIED_SEARCH_CRAWLER,
                "R2-search-verified",
                "search crawler, verified",
            )
        return out(
            TrafficClass.OTHER_IDENTIFIABLE_BOT,
            "R3-search-unverified",
            "claims search crawler, unverified",
        )
    if registry_category in (RegistryCategory.AI_CRAWLER, RegistryCategory.AGENT_CLIENT):
        return out(
            TrafficClass.KNOWN_AI_CRAWLER,
            "R4-ai-agent",
            f"AI crawler or agent client, {str(verdict).lower()}",
        )
    if registry_category in (RegistryCategory.OTHER_BOT, RegistryCategory.AUTOMATION_TOOL):
        return out(
            TrafficClass.OTHER_IDENTIFIABLE_BOT, "R5-other-bot", f"{registry_category} in registry"
        )
    if ua_type == UaType.LIBRARY:
        return out(TrafficClass.OTHER_IDENTIFIABLE_BOT, "R5-library-ua", "library user agent")
    if ua_type == UaType.BOT:
        return out(TrafficClass.OTHER_IDENTIFIABLE_BOT, "R5-other-bot", "bot words in user agent")
    if ua_type == UaType.HEADLESS:
        return out(TrafficClass.BROWSER_AUTOMATION, "R6-automation", "headless browser user agent")
    if ua_type == UaType.BROWSER and edge_signal == EdgeSignal.BOT:
        return out(
            TrafficClass.BROWSER_AUTOMATION, "R6-automation", "browser UA, CDN flags it as bot"
        )
    if ua_type == UaType.BROWSER and edge_signal == EdgeSignal.HUMAN:
        return out(TrafficClass.ORDINARY_BROWSER, "R7-browser-human", "browser UA, CDN says human")
    if ua_type == UaType.BROWSER:
        return out(TrafficClass.UNKNOWN, "R8-unknown", "browser UA, not confirmed human")
    return out(TrafficClass.UNKNOWN, "R8-unknown", "no identifying signal")
