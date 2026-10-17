import csv
import json
from datetime import UTC, datetime

from src.services.importer.adapters import ParsedLine, Reject
from src.services.importer.adapters.common import (
    clean,
    to_int,
    validate,
)
from src.services.site_config import load_cdn_field_map
from src.store.inbox import MAX_LINE_CHARS

FORMATS = ("json", "csv", "tsv")


def load_field_map(name: str) -> dict:
    return load_cdn_field_map(name)


def _timestamp(value: object) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if (
            isinstance(value, int | float)
            or str(value).strip().lstrip("-").replace(".", "", 1).isdigit()
        ):
            number = float(value)
            if number > 1e11:  # epoch milliseconds
                number /= 1000
            return datetime.fromtimestamp(number, UTC)
        ts = datetime.fromisoformat(str(value).strip())
    except ValueError, OverflowError, OSError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _edge_signal(block: dict | None, record: dict) -> str:
    if not block:
        return "none"
    raw = record.get(block["column"])
    try:
        score = float(raw)
    except TypeError, ValueError:
        return "none"
    return "bot" if score < float(block["bot_below"]) else "human"


def _text(record: dict, field_map: dict, key: str) -> str | None:
    column = field_map.get(key)
    if not column:
        return None
    value = record.get(column)
    return None if value is None else str(value)


def _convert(record: dict, line_no: int, field_map: dict) -> ParsedLine | Reject:
    status = record.get(field_map.get("status"))
    size = _text(record, field_map, "bytes")
    return validate(
        line_no,
        ts=_timestamp(record.get(field_map.get("timestamp"))),
        method=(_text(record, field_map, "method") or "").strip().upper() or None,
        path=_text(record, field_map, "path"),
        status=to_int(status),
        bytes_sent=to_int(size) if clean(size) else 0,
        client_ip=_text(record, field_map, "client_ip"),
        user_agent=clean(_text(record, field_map, "user_agent")),
        edge_request_id=clean(_text(record, field_map, "edge_request_id")),
        host=clean(_text(record, field_map, "host")),
        referrer=clean(_text(record, field_map, "referrer")),
        edge_signal=_edge_signal(field_map.get("edge_bot"), record),
    )


def make_parser(field_map: dict):
    fmt = field_map.get("format", "json")
    if fmt not in FORMATS:
        raise ValueError(f"unsupported CDN log format: {fmt}")
    delimiter = "\t" if fmt == "tsv" else ","
    state: dict = {"columns": list(field_map["columns"]) if field_map.get("columns") else None}
    has_header = field_map.get("header", True) and not state["columns"]

    def parse(line: str, line_no: int) -> ParsedLine | Reject | None:
        if not line.strip():
            return None
        if len(line) > MAX_LINE_CHARS:
            return Reject(line_no, "line too long")
        if fmt == "json":
            try:
                record = json.loads(line)
            except ValueError:
                return Reject(line_no, "invalid json")
            if not isinstance(record, dict):
                return Reject(line_no, "json line is not an object")
            return _convert(record, line_no, field_map)
        try:
            values = next(csv.reader([line], delimiter=delimiter))
        except csv.Error, StopIteration:
            return Reject(line_no, "invalid csv")
        if state["columns"] is None:
            if not has_header:
                return Reject(line_no, "no column names")
            state["columns"] = [v.strip() for v in values]
            return None
        if len(values) != len(state["columns"]):
            return Reject(line_no, "wrong column count")
        return _convert(dict(zip(state["columns"], values, strict=True)), line_no, field_map)

    return parse
