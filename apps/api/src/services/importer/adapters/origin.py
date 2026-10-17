from src.services.importer.adapters import ParsedLine, Reject


def parse_line(line: str, line_no: int, request_id_header: str | None) -> ParsedLine | Reject:
    raise NotImplementedError
