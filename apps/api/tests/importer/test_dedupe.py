from dataclasses import replace
from datetime import UTC, datetime

from src.services.importer.adapters import ParsedLine
from src.services.importer.dedupe import line_key

BASE = ParsedLine(
    ts=datetime(2026, 10, 17, 12, tzinfo=UTC),
    method="GET",
    path="/a",
    status=200,
    bytes_sent=1,
    client_ip="1.2.3.4",
    user_agent="ua",
)


def test_same_line_same_key():
    assert line_key(BASE) == line_key(replace(BASE, bytes_sent=999, user_agent="other"))


def test_each_part_changes_key():
    keys = {
        line_key(BASE),
        line_key(replace(BASE, edge_request_id="r1")),
        line_key(replace(BASE, ts=BASE.ts.replace(second=1))),
        line_key(replace(BASE, method="POST")),
        line_key(replace(BASE, path="/b")),
        line_key(replace(BASE, status=404)),
        line_key(replace(BASE, client_ip="1.2.3.5")),
    }
    assert len(keys) == 7


def test_key_uses_utc():
    other = replace(BASE, ts=BASE.ts.astimezone(UTC))
    assert line_key(other) == line_key(BASE)
