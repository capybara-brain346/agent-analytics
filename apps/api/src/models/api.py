from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from src.models.domain import Lane


class LaneHealth(BaseModel):
    site_id: str
    lane: Lane
    last_success: datetime | None
    healthy: bool


class Health(BaseModel):
    healthy: bool
    lanes: list[LaneHealth]


class IngestAccepted(BaseModel):
    file_id: str
    duplicate: bool = False


# ---------------------------------------------------------------- dashboard read API
# JSON is snake_case. Times are ISO 8601 UTC. Every label is lowercase:
# "observed" | "inferred" | "unknown". Lists use Paged[...].

Label = Literal["observed", "inferred", "unknown"]

CLASS_NAMES = {
    1: "Verified search crawler",
    2: "Known AI crawler",
    3: "Other identifiable bot",
    4: "Browser automation / agent-like",
    5: "Ordinary browser",
    6: "Unknown",
}
PATTERN_NAMES = {
    "P1": "Product discovery",
    "P2": "Blocked access",
    "P3": "Broken navigation",
    "P4": "Content discoverability",
    "P5": "Full-journey simulation",
}


class PageInfo(BaseModel):
    limit: int
    offset: int
    total: int
    next_offset: int | None


class Paged[T](BaseModel):
    items: list[T]
    page: PageInfo


class ErrorBody(BaseModel):
    code: str
    message: str


class Window(BaseModel):
    site: str
    start: datetime
    end: datetime
    classes: list[int]


# ---- overview
class KeyNumber(BaseModel):
    value: float | int | None
    previous: float | int | None
    change_pct: float | None
    unit: Literal["requests", "percent", "agents"]
    label: Label = "observed"


class ClassRow(BaseModel):
    traffic_class: int
    name: str
    requests: int
    share_pct: float
    high: int
    medium: int
    low: int
    label: Label = "observed"


class TrendPoint(BaseModel):
    bucket: datetime
    total: int
    by_class: dict[str, int]


class TopAgent(BaseModel):
    agent: str
    traffic_class: int
    requests: int


class TopPage(BaseModel):
    path: str
    agent_requests: int
    errors: int
    blocks: int


class Freshness(BaseModel):
    state: Literal["ok", "updating", "last_run_failed", "alert_failing", "alert_no_data", "no_runs"]
    text: str
    data_up_to: datetime | None
    last_import_at: datetime | None
    latest_run_id: str | None
    failed_step: str | None
    consecutive_failures: int


class AlertOut(BaseModel):
    id: int
    kind: str
    source: str | None
    message: str
    raised_at: datetime
    resolved_at: datetime | None


class Coverage(BaseModel):
    sources_configured: list[str]
    sources_present: list[str]
    paired_share_pct: float | None
    unknown_share_pct: float | None
    cannot_see: list[str]
    partial: list[str]
    label: Label = "observed"


class RecommendationBrief(BaseModel):
    id: int
    rank: int | None
    target: str
    pattern: str
    pattern_name: str
    score: float
    confidence: str
    change: str | None


class Overview(BaseModel):
    window: Window
    empty: bool
    freshness: Freshness
    key_numbers: dict[str, KeyNumber]
    traffic_by_class: list[ClassRow]
    unclassified_requests: int
    trend: list[TrendPoint]
    top_agents: list[TopAgent]
    top_pages: list[TopPage]
    top_recommendations: list[RecommendationBrief]
    coverage: Coverage
    open_alerts_count: int
    open_alerts: list[AlertOut]


# ---- recommendations
class Factor(BaseModel):
    value: float
    why: str | None


class Priority(BaseModel):
    score: float
    formula: str
    factors: dict[str, Factor]


class EvidenceRef(BaseModel):
    sessions_count: int
    events_count: int
    session_ids: list[str]
    event_ids: list[int]
    label: Label = "observed"


class RunHeader(BaseModel):
    id: int
    site: str
    status: str
    window_size: str
    window_start: datetime
    window_end: datetime
    created_at: datetime
    finished_at: datetime | None
    rule_version: str | None
    prompt_version: str | None
    model: str | None
    compared_with_run_id: int | None
    counts: dict[str, int]
    error: str | None


class RecommendationItem(BaseModel):
    id: int
    run_id: int
    stable_id: str
    rank: int | None
    change: str | None
    pattern: str
    pattern_name: str
    journey_id: str | None
    target: str
    recommended_test: str | None
    priority: Priority
    confidence: str
    sessions_count: int
    events_count: int
    text_source: str


class RecommendationList(BaseModel):
    run: RunHeader | None
    empty_reason: Literal["no_run", "no_candidates"] | None
    items: list[RecommendationItem]
    gone: list[RecommendationItem]


class LabeledText(BaseModel):
    text: str | None
    label: Label


class HistoryEntry(BaseModel):
    run_id: int
    recommendation_id: int
    rank: int | None
    score: float
    change: str | None


class RecommendationDetail(RecommendationItem):
    reason: LabeledText
    evidence: EvidenceRef
    potential_issue: LabeledText
    suggested_validation: LabeledText
    next_action: LabeledText
    model: str | None
    prompt_version: str | None
    text_source_note: str
    fact_bundle: dict[str, Any]
    history: list[HistoryEntry]
    first_seen_run_id: int
    related: list[RecommendationBrief]
    run: RunHeader


class GenerateResult(BaseModel):
    status: Literal["completed"]
    run: RunHeader | None


# ---- agents
class AgentRow(BaseModel):
    agent_id: str
    name: str
    vendor: str | None
    traffic_class: int
    class_name: str
    verification: str | None
    verification_note: str
    confidence: str | None
    first_seen: datetime | None
    last_seen: datetime | None
    requests: int
    sessions: int
    distinct_pages: int
    common_paths: list[str]
    label: Label = "observed"


class VerdictRow(BaseModel):
    id: int
    checked_at: datetime
    verdict: str
    method: str
    evidence: str | None
    registry_version: str | None
    ip_snapshot_version: str | None
    claimed_agent: str | None
    client_key: str
    user_agent: str | None
    client_ip: str | None
    edge_signal: str
    traffic_class: int | None
    confidence: str | None
    rule_id: str | None
    rule_version: str | None
    class_evidence: str | None
    flags: list[str]
    ua_type: str | None
    registry_category: str | None
    events_link: str


class ClientKeyRow(BaseModel):
    client_key: str
    user_agent: str | None
    client_ip: str | None
    shared_ip: bool


class AgentDetail(BaseModel):
    agent: AgentRow
    why_this_class: dict[str, Any]
    verdict_history: list[VerdictRow]
    client_keys: list[ClientKeyRow]
    activity: list[dict[str, Any]]
    top_paths: list[dict[str, Any]]
    status_mix: list[dict[str, Any]]
    sessions: list[SessionRow]


# ---- events
class EventRow(BaseModel):
    id: int
    ts: datetime
    method: str | None
    host: str | None
    path: str
    status: int | None
    edge_status: int | None
    origin_status: int | None
    source: str
    pair_state: str
    client_key: str | None
    user_agent: str | None
    client_ip: str | None
    verdict_id: int | None
    claimed_agent: str | None
    verdict: str | None
    confidence: str | None
    traffic_class: int | None
    class_name: str | None
    session_id: str | None


class SessionLink(BaseModel):
    session_id: str
    position: int
    of: int


class EventDetail(BaseModel):
    id: int
    request: dict[str, Any]
    request_label: Label = "observed"
    source: dict[str, Any]
    verdict: VerdictRow | None
    classification: dict[str, Any] | None
    session: SessionLink | None
    import_file: dict[str, Any] | None
    recommendations: list[dict[str, Any]]


# ---- sessions
class SessionRow(BaseModel):
    session_id: str
    client_key: str
    agent: str | None
    traffic_class: int | None
    class_name: str | None
    confidence: str | None
    started: datetime
    last_seen: datetime
    state: Literal["in_progress", "closed"]
    in_progress: bool
    last_event_age_seconds: int | None
    requests: int
    distinct_pages: int
    has_retry: bool
    has_loop: bool
    reached_conversion: bool
    journeys_reached: dict[str, int]
    label: Label = "observed"


class SessionStep(BaseModel):
    seq: int
    event_id: int
    ts: datetime
    path: str
    method: str | None
    status: int | None
    delta_seconds: float | None
    flags: list[str]


class Gap(BaseModel):
    text: str
    label: Label


class SessionDetail(BaseModel):
    session: SessionRow
    facts: dict[str, Any]
    facts_label: Label = "observed"
    grouping: LabeledText
    confidence_reason: LabeledText
    steps: list[SessionStep]
    outcome: LabeledText
    gaps: list[Gap]
    recommendations: list[dict[str, Any]]


# ---- pages
class PageRow(BaseModel):
    path: str
    tags: list[str]
    agent_requests: int
    requests: int
    sessions: int
    distinct_agents: int
    error_rate_pct: float | None
    block_rate_pct: float | None
    retries: int
    median_bytes: int | None
    label: Label = "observed"


class PageList(BaseModel):
    view: str | None
    items: list[PageRow]


class PageDetail(BaseModel):
    page: PageRow
    in_sitemap: bool
    access_policy: Literal["allowed", "blocked_by_intent"]
    by_class: list[dict[str, Any]]
    over_time: list[dict[str, Any]]
    agents: list[dict[str, Any]]
    sessions: list[SessionRow]
    recommendations: list[dict[str, Any]]


# ---- journeys
class JourneyClassRow(BaseModel):
    traffic_class: int
    class_name: str
    sessions: int
    reached: list[int]
    stopped_at: list[int]
    retry_or_loop: list[int]
    label: Label = "observed"


class JourneyOut(BaseModel):
    journey_id: str
    critical: bool
    steps: list[str]
    by_class: list[JourneyClassRow]
    outcome: LabeledText


# ---- pipeline runs
class PipelineRunOut(BaseModel):
    id: str
    site: str
    lane: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    failed_step: str | None
    error: str | None
    counts: dict[str, Any]
