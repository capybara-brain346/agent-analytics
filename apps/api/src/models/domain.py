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
