from datetime import UTC, datetime

from src.services.importer.adapters import ParsedLine, Reject
from src.services.importer.adapters.origin import parse_line

CHROME = "Mozilla/5.0 (X11; Linux x86_64) Chrome/126.0"


def line(
    ip="20.171.1.5",
    ts="17/Oct/2026:12:00:00 +0000",
    request="GET /pricing HTTP/1.1",
    status="200",
    size="5120",
    ref="-",
    ua="GPTBot/1.2",
    extra="",
):
    return f'{ip} - - [{ts}] "{request}" {status} {size} "{ref}" "{ua}"{extra}'


def test_combined_line():
    p = parse_line(line(), 1, None)
    assert p == ParsedLine(
        ts=datetime(2026, 10, 17, 12, 0, tzinfo=UTC),
        method="GET",
        path="/pricing",
        status=200,
        bytes_sent=5120,
        client_ip="20.171.1.5",
        user_agent="GPTBot/1.2",
    )


def test_timezone_offset_converted_to_utc():
    p = parse_line(line(ts="17/Oct/2026:14:00:00 +0200"), 1, None)
    assert p.ts == datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def test_ipv6_and_dash_values():
    p = parse_line(line(ip="2001:db8::1", size="-", ref="-", ua="-"), 1, None)
    assert p.client_ip == "2001:db8::1"
    assert p.bytes_sent == 0
    assert p.user_agent == ""
    assert p.referrer is None


def test_referrer_kept():
    p = parse_line(line(ref="https://example.com/a?b=1"), 1, None)
    assert p.referrer == "https://example.com/a?b=1"


def test_request_id_and_request_time():
    p = parse_line(line(extra=' "e7-abc" 0.123'), 1, "X-Request-ID")
    assert p.edge_request_id == "e7-abc"
    assert p.request_id is None
    assert p.response_time_ms == 123


def test_request_id_dash_is_none():
    p = parse_line(line(extra=' "-" 0.005'), 1, "X-Request-ID")
    assert p.edge_request_id is None
    assert p.response_time_ms == 5


def test_request_id_ignored_without_header_setting():
    p = parse_line(line(extra=' "e7-abc"'), 1, None)
    assert p.edge_request_id is None


def test_request_time_only():
    p = parse_line(line(extra=" 1.5"), 1, None)
    assert p.response_time_ms == 1500


def test_path_with_query_and_spaces():
    p = parse_line(line(request="GET /a b?x=1 HTTP/2.0"), 1, None)
    assert p.path == "/a b?x=1"


def test_http09_request_without_protocol():
    p = parse_line(line(request="GET /x"), 1, None)
    assert p.path == "/x"


def test_bad_lines_reject_without_text():
    secret = "SECRET-TEXT"
    cases = [
        f"garbage {secret}",
        "",
        line(request="-"),
        line(request=f"\\x16\\x03\\x01{secret}"),
        line(status="-"),
        line(status="99"),
        line(status="600"),
        line(ts="not-a-time"),
        line(ip="not-an-ip"),
        line(ip="-"),
        line(request="GET  HTTP/1.1"),
        line(request="get /x HTTP/1.1"),
        line(request="GET /" + "a" * 9000 + " HTTP/1.1"),
        line(ua="u" * 3000),
        "x" * 100_000,
    ]
    for i, text in enumerate(cases, start=7):
        r = parse_line(text, i, None)
        assert isinstance(r, Reject), text[:40]
        assert r.line_no == i
        assert secret not in r.reason
        assert len(r.reason) <= 200


def test_limits_at_boundary_ok():
    assert isinstance(
        parse_line(line(request="GET /" + "a" * 8191 + " HTTP/1.1"), 1, None), ParsedLine
    )
    assert isinstance(parse_line(line(ua="u" * 2048), 1, None), ParsedLine)
