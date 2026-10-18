import re
from datetime import datetime
from functools import lru_cache

from src.services.importer.adapters import ParsedLine, Reject
from src.services.importer.adapters.common import clean, to_int, validate
from src.store.inbox import MAX_LINE_CHARS

# nginx "combined", then an optional quoted forwarded request ID and an optional $request_time.
LINE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] "(?P<request>[^"]*)" (?P<status>\S+) (?P<size>\S+)'
    r' "(?P<referrer>[^"]*)" "(?P<ua>[^"]*)"'
    r'(?: "(?P<rid>[^"]*)")?(?: (?P<rtime>[0-9.]+|-))?\s*$'
)


@lru_cache(maxsize=4096)
def _time(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def _split_request(request: str) -> tuple[str | None, str | None]:
    parts = request.split(" ")
    if len(parts) < 2:
        return None, None
    if len(parts) >= 3 and parts[-1].startswith("HTTP/"):
        parts = parts[:-1]
    return parts[0], " ".join(parts[1:])


def _millis(text: str | None) -> int | None:
    if not text or text == "-":
        return None
    try:
        return round(float(text) * 1000)
    except ValueError:
        return None


def parse_line(line: str, line_no: int, request_id_header: str | None) -> ParsedLine | Reject:
    if len(line) > MAX_LINE_CHARS:
        return Reject(line_no, "line too long")
    m = LINE.match(line)
    if m is None:
        return Reject(line_no, "not a combined log line")
    method, path = _split_request(m["request"])
    size = m["size"]
    if size != "-" and to_int(size) is None:
        return Reject(line_no, "invalid size")
    return validate(
        line_no,
        ts=_time(m["time"]),
        method=method,
        path=path,
        status=to_int(m["status"]),
        bytes_sent=0 if size == "-" else to_int(size),
        client_ip=m["ip"],
        user_agent=clean(m["ua"]),
        edge_request_id=clean(m["rid"]) if request_id_header else None,
        referrer=clean(m["referrer"]),
        response_time_ms=_millis(m["rtime"]),
    )


def make_parser(request_id_header: str | None):
    def parse(line: str, line_no: int) -> ParsedLine | Reject | None:
        if not line.strip():
            return None
        return parse_line(line, line_no, request_id_header)

    return parse
