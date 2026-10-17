"""CDN log adapter. Vendor columns come only from `config/cdn/<vendor>.yaml` (decision 1b.4)."""

from src.services.adapters import ParsedLine, Reject


def load_field_map(name: str) -> dict:
    raise NotImplementedError


def parse_line(line: str, line_no: int, field_map: dict) -> ParsedLine | Reject:
    raise NotImplementedError
