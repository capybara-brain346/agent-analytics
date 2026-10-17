import hashlib
from datetime import UTC

from src.services.importer.adapters import ParsedLine


def line_key(line: ParsedLine) -> str:
    # Decision 1.8: request ID + timestamp + method + path + status. The client IP is added so two
    # different clients that hit one path in the same second are not merged when there is no ID.
    parts = (
        line.edge_request_id or line.request_id or "",
        line.ts.astimezone(UTC).isoformat(),
        line.method,
        line.path,
        str(line.status),
        line.client_ip,
    )
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]
