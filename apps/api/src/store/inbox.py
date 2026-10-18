import asyncio
import codecs
import hashlib
import zlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from functools import lru_cache
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from src.config import Settings, get_settings

GZIP_MAGIC = b"\x1f\x8b"
MAX_LINE_CHARS = 64 * 1024  # A longer line is cut to MAX_LINE_CHARS + 1 chars; adapters reject it
DECOMPRESS_CHUNK = 1024 * 1024


class ObjectNotFound(KeyError):
    pass


class ObjectTooLarge(ValueError):
    pass


class Inbox(ABC):
    @abstractmethod
    async def ensure_bucket(self) -> None: ...

    @abstractmethod
    async def put_stream(self, key: str, chunks: AsyncIterator[bytes]) -> tuple[str, int]:
        # Store the chunks as one object. Returns (sha256 hex of the bytes, size in bytes).
        ...

    @abstractmethod
    def open_lines(self, key: str) -> AsyncIterator[str]:
        # Yield decoded text lines without the line end. Gunzip when the object is gzip
        # (magic bytes 1f 8b). Raise ObjectNotFound when the key does not exist.
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        # No error when the key does not exist.
        ...


def is_missing(error: ClientError) -> bool:
    code = str(error.response.get("Error", {}).get("Code", ""))
    return code in {"NoSuchKey", "404", "NotFound", "NoSuchBucket"}


class S3Inbox(Inbox):
    def __init__(
        self, settings: Settings, client: Any = None, part_bytes: int = 8 * 1024 * 1024
    ) -> None:
        self.settings = settings
        self.bucket = settings.s3_bucket
        self.part_bytes = max(part_bytes, 1)
        self._client = client
        self._bucket_ready = False

    @property
    def client(self) -> Any:
        if self._client is None:
            s = self.settings
            self._client = boto3.client(
                "s3",
                endpoint_url=s.s3_endpoint_url,
                region_name=s.s3_region,
                aws_access_key_id=s.s3_access_key_id,
                aws_secret_access_key=s.s3_secret_access_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
            )
        return self._client

    async def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        await asyncio.to_thread(self._ensure_bucket)
        self._bucket_ready = True

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            if not is_missing(error):
                raise
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError as create_error:
                code = create_error.response.get("Error", {}).get("Code")
                if code not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                    raise

    async def put_stream(
        self, key: str, chunks: AsyncIterator[bytes], max_bytes: int | None = None
    ) -> tuple[str, int]:
        await self.ensure_bucket()
        digest = hashlib.sha256()
        size = 0
        buffer = bytearray()
        upload_id: str | None = None
        parts: list[dict] = []
        part_size = self.part_bytes
        try:
            async for chunk in chunks:
                size += len(chunk)
                if max_bytes is not None and size > max_bytes:
                    raise ObjectTooLarge(f"object is larger than {max_bytes} bytes")
                digest.update(chunk)
                buffer.extend(chunk)
                while len(buffer) >= part_size:
                    if upload_id is None:
                        upload_id = await asyncio.to_thread(self._start_upload, key)
                    data = bytes(buffer[:part_size])
                    del buffer[:part_size]
                    parts.append(await self._send_part(key, upload_id, len(parts) + 1, data))
            if upload_id is None:
                await asyncio.to_thread(
                    self.client.put_object, Bucket=self.bucket, Key=key, Body=bytes(buffer)
                )
            else:
                if buffer:
                    parts.append(
                        await self._send_part(key, upload_id, len(parts) + 1, bytes(buffer))
                    )
                await asyncio.to_thread(
                    self.client.complete_multipart_upload,
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )
        except BaseException:
            if upload_id is not None:
                await asyncio.shield(asyncio.to_thread(self._abort, key, upload_id))
            raise
        return digest.hexdigest(), size

    def _start_upload(self, key: str) -> str:
        return self.client.create_multipart_upload(Bucket=self.bucket, Key=key)["UploadId"]

    async def _send_part(self, key: str, upload_id: str, number: int, data: bytes) -> dict:
        response = await asyncio.to_thread(
            self.client.upload_part,
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=number,
            Body=data,
        )
        return {"ETag": response["ETag"], "PartNumber": number}

    def _abort(self, key: str, upload_id: str) -> None:
        try:
            self.client.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
        except ClientError:
            pass

    async def _read_raw(self, bucket: str, key: str) -> AsyncIterator[bytes]:
        size = self.settings.ingest_chunk_bytes
        try:
            body = (await asyncio.to_thread(self.client.get_object, Bucket=bucket, Key=key))["Body"]
        except ClientError as error:
            if is_missing(error):
                raise ObjectNotFound(key) from None
            raise
        try:
            while data := await asyncio.to_thread(body.read, size):
                yield data
        finally:
            await asyncio.to_thread(body.close)

    async def open_lines(self, key: str) -> AsyncIterator[str]:
        # Memory is bounded: gunzip output comes in pieces of DECOMPRESS_CHUNK bytes, a line
        # longer than MAX_LINE_CHARS is cut (the adapter rejects it) and total output is capped.
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        splitter = _LineSplitter()
        limit = self.settings.max_decompressed_bytes
        gunzip: Any = None
        head = b""
        total = 0

        def pieces(raw: bytes) -> Iterator[str]:
            nonlocal total
            for data in gunzip.feed(raw) if gunzip else (raw,):
                total += len(data)
                if total > limit:
                    raise ObjectTooLarge(f"file is larger than {limit} bytes after gunzip")
                yield decoder.decode(data)

        async for raw in self._read_raw(self.bucket, key):
            if gunzip is None:
                head += raw
                if len(head) < 2:
                    continue
                raw, head = head, b""
                gunzip = _Gunzip() if raw[:2] == GZIP_MAGIC else False
            for text in pieces(raw):
                for line in splitter.feed(text):
                    yield line
        if gunzip is None and head:
            gunzip = False
            for text in pieces(head):
                for line in splitter.feed(text):
                    yield line
        for line in splitter.feed(decoder.decode(b"", final=True)):
            yield line
        for line in splitter.finish():
            yield line

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def list_objects(self, prefix: str = "", bucket: str | None = None) -> list[dict]:
        return await asyncio.to_thread(self._list, bucket or self.bucket, prefix)

    def _list(self, bucket: str, prefix: str) -> list[dict]:
        found: list[dict] = []
        token: str | None = None
        while True:
            args: dict = {"Bucket": bucket, "Prefix": prefix}
            if token:
                args["ContinuationToken"] = token
            page = self.client.list_objects_v2(**args)
            for item in page.get("Contents", []):
                found.append(
                    {
                        "key": item["Key"],
                        "size": item["Size"],
                        "last_modified": item.get("LastModified"),
                        "etag": item.get("ETag"),
                    }
                )
            if not page.get("IsTruncated"):
                return found
            token = page.get("NextContinuationToken")

    async def copy_from(
        self, bucket: str, key: str, dest_key: str | None = None
    ) -> tuple[str, int]:
        # Stream through us: works across endpoints and credentials, and gives the sha256.
        return await self.put_stream(dest_key or key, self._read_raw(bucket, key))


class _Gunzip:
    # Handles files of several gzip members joined together. Output is bounded per step.
    def __init__(self) -> None:
        self.stream = zlib.decompressobj(31)

    def feed(self, raw: bytes) -> Iterator[bytes]:
        while raw:
            out = self.stream.decompress(raw, DECOMPRESS_CHUNK)
            if out:
                yield out
            if self.stream.eof:
                raw = self.stream.unused_data
                self.stream = zlib.decompressobj(31)
            else:
                raw = self.stream.unconsumed_tail


class _LineSplitter:
    def __init__(self) -> None:
        self.tail = ""
        self.skipping = False

    def feed(self, text: str) -> list[str]:
        out: list[str] = []
        parts = text.split("\n")
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            if self.skipping:
                self.skipping = last
                continue
            line = self.tail + part
            self.tail = ""
            if len(line) > MAX_LINE_CHARS:
                out.append(line[: MAX_LINE_CHARS + 1])
                self.skipping = last
            elif last:
                self.tail = line
            else:
                out.append(line.removesuffix("\r"))
        return out

    def finish(self) -> list[str]:
        line, self.tail = self.tail, ""
        return [line.removesuffix("\r")] if line else []


@lru_cache
def get_inbox() -> Inbox:
    return S3Inbox(get_settings())
