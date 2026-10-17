from collections.abc import AsyncIterator

from src.config import Settings


class Inbox:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def ensure_bucket(self) -> None:
        raise NotImplementedError

    async def put_stream(self, key: str, chunks: AsyncIterator[bytes]) -> tuple[str, int]:
        raise NotImplementedError

    async def open_lines(self, key: str) -> AsyncIterator[str]:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError
