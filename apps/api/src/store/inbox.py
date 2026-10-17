"""Inbox: raw log files in S3-compatible storage (decision 1.19).

Same code for AWS S3, the customer's S3-compatible storage and SeaweedFS.
"""

from collections.abc import AsyncIterator

from src.config import Settings


class Inbox:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def ensure_bucket(self) -> None:
        raise NotImplementedError

    async def put_stream(self, key: str, chunks: AsyncIterator[bytes]) -> tuple[str, int]:
        """Stream parts to storage. Return (sha256, size) calculated during the stream."""
        raise NotImplementedError

    async def open_lines(self, key: str) -> AsyncIterator[str]:
        """Read a (gzip) file one line at a time (decision 1.6)."""
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError
