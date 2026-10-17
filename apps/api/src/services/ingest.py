"""Flow 1 entry: stream a request body to the inbox, register it in `import_files` (1.15).

No parsing in the request. The worker imports the file on its next tick.
"""

from collections.abc import AsyncIterator

from src.models.domain import FilePriority


async def accept_chunk(
    site_id: str, body: AsyncIterator[bytes], priority: FilePriority
) -> tuple[str, bool]:
    """Return (file_id, duplicate). Duplicate sha256 → delete the object (S.6)."""
    raise NotImplementedError


async def check_site_token(site_id: str, token: str) -> bool:
    raise NotImplementedError


async def check_rate_limit(site_id: str, size_hint: int | None) -> bool:
    """Rate limit and byte quota for each site; over → 429 (decision 1.16)."""
    raise NotImplementedError
