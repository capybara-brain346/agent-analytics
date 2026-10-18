import gzip
import hashlib
import zlib
from collections.abc import AsyncIterator

from src.store.inbox import Inbox, ObjectNotFound


class MemoryInbox(Inbox):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes, *, gzipped: bool = False) -> tuple[str, int]:
        if gzipped:
            data = gzip.compress(data)
        self.objects[key] = data
        return hashlib.sha256(data).hexdigest(), len(data)

    def put_text(self, key: str, text: str, *, gzipped: bool = False) -> tuple[str, int]:
        return self.put_bytes(key, text.encode(), gzipped=gzipped)

    async def ensure_bucket(self) -> None:
        return None

    async def put_stream(self, key: str, chunks: AsyncIterator[bytes]) -> tuple[str, int]:
        digest = hashlib.sha256()
        parts = []
        async for chunk in chunks:
            digest.update(chunk)
            parts.append(chunk)
        self.objects[key] = b"".join(parts)
        return digest.hexdigest(), len(self.objects[key])

    async def open_lines(self, key: str) -> AsyncIterator[str]:
        try:
            data = self.objects[key]
        except KeyError:
            raise ObjectNotFound(key) from None
        if data[:2] == b"\x1f\x8b":
            data = zlib.decompress(data, 31)
        for line in data.decode("utf-8", errors="replace").splitlines():
            yield line

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
