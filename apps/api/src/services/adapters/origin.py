"""nginx origin log adapter. Client IP = real_ip value (decision 1b.2)."""

from src.services.adapters import ParsedLine, Reject


def parse_line(line: str, line_no: int, request_id_header: str | None) -> ParsedLine | Reject:
    raise NotImplementedError
