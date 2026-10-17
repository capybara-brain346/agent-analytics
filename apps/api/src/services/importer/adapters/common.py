import ipaddress
import re
from datetime import UTC, datetime

from src.services.importer.adapters import ParsedLine, Reject

MAX_PATH_CHARS = 8 * 1024
MAX_UA_CHARS = 2 * 1024
MAX_ID_CHARS = 200
MAX_REFERRER_CHARS = 2 * 1024
MIN_YEAR, MAX_YEAR = 2000, 2100

METHOD = re.compile(r"^[A-Z]{1,16}$")


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return None if value in ("", "-") else value


def check_ip(value: str | None) -> str | None:
    value = clean(value)
    if value is None:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def to_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except TypeError, ValueError:
        return None


BIGINT_MAX = 2**63 - 1
INT_MAX = 2**31 - 1


def bad_text(value: object) -> bool:
    # Postgres text cannot hold NUL; a lone surrogate cannot be encoded as UTF-8.
    if not isinstance(value, str):
        return False
    if "\x00" in value:
        return True
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return True
    return False


def validate(
    line_no: int,
    *,
    ts: datetime | None,
    method: str | None,
    path: str | None,
    status: int | None,
    bytes_sent: int | None,
    client_ip: str | None,
    user_agent: str | None,
    **extra,
) -> ParsedLine | Reject:
    def reject(reason: str) -> Reject:
        return Reject(line_no, reason)

    if ts is None or not MIN_YEAR <= ts.year <= MAX_YEAR:
        return reject("invalid timestamp")
    if status is None or not 100 <= status <= 599:
        return reject("invalid status")
    if method is None or not METHOD.match(method):
        return reject("invalid method")
    if not path:
        return reject("missing path")
    if len(path) > MAX_PATH_CHARS:
        return reject("path too long")
    texts = (method, path, client_ip, user_agent, *(v for v in extra.values()))
    if any(bad_text(v) for v in texts):
        return reject("invalid character")
    if bytes_sent is not None and bytes_sent > BIGINT_MAX:
        return reject("invalid size")
    response_time = extra.get("response_time_ms")
    if response_time is not None and not 0 <= response_time <= INT_MAX:
        return reject("invalid response time")
    ip = check_ip(client_ip)
    if ip is None:
        return reject("invalid client ip")
    user_agent = user_agent or ""
    if len(user_agent) > MAX_UA_CHARS:
        return reject("user agent too long")
    for key in ("request_id", "edge_request_id"):
        if extra.get(key) and len(extra[key]) > MAX_ID_CHARS:
            return reject("request id too long")
    if extra.get("referrer") and len(extra["referrer"]) > MAX_REFERRER_CHARS:
        extra["referrer"] = extra["referrer"][:MAX_REFERRER_CHARS]
    return ParsedLine(
        ts=ts.astimezone(UTC),
        method=method,
        path=path,
        status=status,
        bytes_sent=max(bytes_sent or 0, 0),
        client_ip=ip,
        user_agent=user_agent,
        **extra,
    )
