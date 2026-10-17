from collections.abc import AsyncIterator

from src.models.domain import FilePriority


async def accept_chunk(
    site_id: str, body: AsyncIterator[bytes], priority: FilePriority
) -> tuple[str, bool]:
    raise NotImplementedError


async def check_site_token(site_id: str, token: str) -> bool:
    raise NotImplementedError


async def check_rate_limit(site_id: str, size_hint: int | None) -> bool:
    raise NotImplementedError
