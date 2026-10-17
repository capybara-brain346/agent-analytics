import json
from datetime import UTC, datetime

import pytest

from src.services.importer.adapters import ParsedLine, Reject
from src.services.importer.adapters.cdn import load_field_map, make_parser

FIELD_MAP = {
    "format": "json",
    "edge_request_id": "RayID",
    "timestamp": "EdgeStartTimestamp",
    "client_ip": "ClientIP",
    "method": "ClientRequestMethod",
    "path": "ClientRequestURI",
    "status": "EdgeResponseStatus",
    "bytes": "EdgeResponseBytes",
    "user_agent": "ClientRequestUserAgent",
    "edge_bot": {"column": "BotScore", "bot_below": 30},
}

RECORD = {
    "RayID": "8a1b2c3d4e5f",
    "EdgeStartTimestamp": "2026-10-17T12:00:00Z",
    "ClientIP": "20.171.1.5",
    "ClientRequestMethod": "GET",
    "ClientRequestURI": "/pricing?plan=pro",
    "EdgeResponseStatus": 403,
    "EdgeResponseBytes": 312,
    "ClientRequestUserAgent": "GPTBot/1.2",
    "BotScore": 5,
}
TS = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def test_json_line():
    p = make_parser(FIELD_MAP)(json.dumps(RECORD), 1)
    assert p == ParsedLine(
        ts=TS,
        method="GET",
        path="/pricing?plan=pro",
        status=403,
        bytes_sent=312,
        client_ip="20.171.1.5",
        user_agent="GPTBot/1.2",
        edge_request_id="8a1b2c3d4e5f",
        edge_signal="bot",
    )


@pytest.mark.parametrize(
    ("score", "signal"),
    [(5, "bot"), (29, "bot"), (30, "human"), (99, "human"), ("12", "bot"), (None, "none"),
     ("", "none"), ("n/a", "none")],
)  # fmt: skip
def test_edge_bot_threshold(score, signal):
    rec = RECORD | {"BotScore": score}
    assert make_parser(FIELD_MAP)(json.dumps(rec), 1).edge_signal == signal


def test_no_edge_bot_block_gives_none_signal():
    fm = {k: v for k, v in FIELD_MAP.items() if k != "edge_bot"}
    assert make_parser(fm)(json.dumps(RECORD), 1).edge_signal == "none"


@pytest.mark.parametrize(
    "value",
    ["2026-10-17T12:00:00Z", "2026-10-17T14:00:00+02:00", "2026-10-17 12:00:00",
     1792238400, "1792238400", 1792238400000, 1792238400.0],
)  # fmt: skip
def test_timestamp_forms(value):
    rec = RECORD | {"EdgeStartTimestamp": value}
    assert make_parser(FIELD_MAP)(json.dumps(rec), 1).ts == TS


def test_bad_json_and_missing_fields_reject():
    parse = make_parser(FIELD_MAP)
    for text in [
        "{not json",
        "[1,2]",
        json.dumps({"RayID": "x"}),
        json.dumps(RECORD | {"EdgeResponseStatus": 7}),
    ]:
        r = parse(text, 3)
        assert isinstance(r, Reject)
        assert r.line_no == 3
        assert "not json" not in r.reason


def test_blank_line_is_skipped():
    assert make_parser(FIELD_MAP)("   ", 1) is None


def test_csv_with_header_row():
    fm = FIELD_MAP | {"format": "csv"}
    parse = make_parser(fm)
    header = ",".join(RECORD)
    row = (
        '8a1b2c3d4e5f,2026-10-17T12:00:00Z,20.171.1.5,GET,"/a,b",200,10,'
        '"Mozilla/5.0 (X11, Linux)",50'
    )
    assert parse(header, 1) is None
    p = parse(row, 2)
    assert p.path == "/a,b"
    assert p.user_agent == "Mozilla/5.0 (X11, Linux)"
    assert p.edge_signal == "human"


def test_tsv_with_header_row():
    fm = FIELD_MAP | {"format": "tsv"}
    parse = make_parser(fm)
    assert parse("\t".join(RECORD), 1) is None
    p = parse("\t".join(str(v) for v in RECORD.values()), 2)
    assert p.status == 403
    assert p.edge_signal == "bot"


def test_csv_without_header_uses_columns_list():
    fm = FIELD_MAP | {"format": "csv", "header": False, "columns": list(RECORD)}
    p = make_parser(fm)(",".join(str(v) for v in RECORD.values()), 1)
    assert p.status == 403


def test_csv_wrong_column_count_rejects():
    fm = FIELD_MAP | {"format": "csv"}
    parse = make_parser(fm)
    parse(",".join(RECORD), 1)
    assert isinstance(parse("a,b", 2), Reject)


def test_load_field_map_from_config(config_dir):
    fm = load_field_map("example")
    assert fm["format"] == "json"
    assert fm["edge_bot"]["bot_below"] == 30
