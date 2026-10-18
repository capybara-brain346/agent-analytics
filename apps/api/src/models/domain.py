from enum import IntEnum, StrEnum


class Lane(StrEnum):
    FAST = "fast"  # 1 Import → 1b Pair → 2 Verify → 3 Classify → 4 Views
    SLOW = "slow"  # 5 Recommendations


class SourceType(StrEnum):
    ORIGIN = "origin"
    CDN = "cdn"


class FileStatus(StrEnum):
    NEW = "new"
    IMPORTING = "importing"
    SUCCESS = "success"
    FAILED = "failed"


class FilePriority(StrEnum):
    LIVE = "live"
    BACKFILL = "backfill"


class Verdict(StrEnum):
    VERIFIED = "VERIFIED"
    CLAIMED = "CLAIMED"
    UNVERIFIED = "UNVERIFIED"
    SPOOFED = "SPOOFED"
    UNKNOWN = "UNKNOWN"


class VerifyMethod(StrEnum):
    IP_LIST = "ip_list"
    RDNS = "rdns"
    NONE = "none"


class EdgeSignal(StrEnum):
    BOT = "bot"
    HUMAN = "human"
    NONE = "none"


class TrafficClass(IntEnum):
    VERIFIED_SEARCH_CRAWLER = 1
    KNOWN_AI_CRAWLER = 2
    OTHER_IDENTIFIABLE_BOT = 3
    BROWSER_AUTOMATION = 4
    ORDINARY_BROWSER = 5
    UNKNOWN = 6


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceLabel(StrEnum):
    OBSERVED = "Observed"
    INFERRED = "Inferred"
    UNKNOWN = "Unknown"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class Pattern(StrEnum):
    P1_PRODUCT_DISCOVERY = "P1"
    P2_BLOCKED_ACCESS = "P2"
    P3_BROKEN_NAVIGATION = "P3"
    P4_CONTENT_DISCOVERY = "P4"
    P5_FULL_JOURNEY = "P5"


class EventSource(StrEnum):
    ORIGIN = "origin"
    CDN = "cdn"
    PAIRED = "paired"


class PairState(StrEnum):
    PENDING = "pending"
    PAIRED = "paired"
    SINGLE = "single"


class UaType(StrEnum):
    BROWSER = "browser"
    HEADLESS = "headless"
    LIBRARY = "library"
    BOT = "bot"
    OTHER = "other"


class RegistryCategory(StrEnum):
    SEARCH_CRAWLER = "search_crawler"
    AI_CRAWLER = "ai_crawler"
    AGENT_CLIENT = "agent_client"
    OTHER_BOT = "other_bot"
    AUTOMATION_TOOL = "automation_tool"


class AlertKind(StrEnum):
    NO_DATA = "no_data"
    FAILED_RUNS = "failed_runs"


class RecommendationChange(StrEnum):
    NEW = "new"
    OPEN = "open"
    GONE = "gone"


class TextSource(StrEnum):
    LLM = "llm"
    TEMPLATE = "template"
