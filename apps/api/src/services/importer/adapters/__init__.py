from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ParsedLine:
    ts: datetime
    method: str
    path: str
    status: int
    bytes_sent: int
    client_ip: str
    user_agent: str
    request_id: str | None = None
    edge_request_id: str | None = None
    edge_signal: str | None = None
    host: str | None = None
    referrer: str | None = None
    response_time_ms: int | None = None


@dataclass(frozen=True)
class Reject:
    line_no: int
    reason: str  # Never the line text (decision 1.7)
