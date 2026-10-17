import gzip
import hashlib

import pytest

from src.config import Settings
from src.store.inbox import ObjectNotFound, ObjectTooLarge, S3Inbox, get_inbox
from tests.ingest.fake_s3 import FakeS3


async def chunks(data: bytes, size: int = 7):
    for i in range(0, len(data), size):
        yield data[i : i + size]


def make(part_bytes: int = 20) -> tuple[S3Inbox, FakeS3]:
    fake = FakeS3()
    settings = Settings(s3_bucket="inbox", ingest_chunk_bytes=5)
    return S3Inbox(settings, client=fake, part_bytes=part_bytes), fake


async def lines(inbox: S3Inbox, key: str) -> list[str]:
    return [line async for line in inbox.open_lines(key)]


async def test_ensure_bucket_creates_once():
    inbox, fake = make()
    await inbox.ensure_bucket()
    await inbox.ensure_bucket()
    assert fake.calls == ["create_bucket"]


async def test_small_object_uses_put_object_and_returns_sha():
    inbox, fake = make()
    data = b"a\nb\n"
    sha, size = await inbox.put_stream("k", chunks(data))
    assert (sha, size) == (hashlib.sha256(data).hexdigest(), len(data))
    assert fake.buckets["inbox"]["k"] == data
    assert "create_multipart_upload" not in fake.calls


async def test_large_object_uses_multipart():
    inbox, fake = make(part_bytes=20)
    data = bytes(range(65, 91)) * 4
    sha, size = await inbox.put_stream("k", chunks(data))
    assert fake.buckets["inbox"]["k"] == data
    assert fake.calls.count("upload_part") == 6
    assert sha == hashlib.sha256(data).hexdigest() and size == len(data)


async def test_max_size_aborts_multipart():
    inbox, fake = make(part_bytes=20)
    with pytest.raises(ObjectTooLarge):
        await inbox.put_stream("k", chunks(b"x" * 100), max_bytes=50)
    assert "abort_multipart_upload" in fake.calls
    assert fake.uploads == {}
    assert "k" not in fake.buckets["inbox"]


async def test_source_error_aborts_multipart():
    inbox, fake = make(part_bytes=10)

    async def broken():
        yield b"x" * 30
        raise RuntimeError("client gone")

    with pytest.raises(RuntimeError):
        await inbox.put_stream("k", broken())
    assert fake.uploads == {}


async def test_open_lines_plain_with_crlf_and_bad_bytes():
    inbox, fake = make()
    await inbox.ensure_bucket()
    fake.buckets["inbox"]["k"] = b"one\r\ntwo \xff\nthree"
    assert await lines(inbox, "k") == ["one", "two �", "three"]


async def test_open_lines_gzip_and_multi_member():
    inbox, fake = make()
    await inbox.ensure_bucket()
    fake.buckets["inbox"]["k"] = gzip.compress(b"a\nb\n") + gzip.compress("cé\n".encode())
    assert await lines(inbox, "k") == ["a", "b", "cé"]


async def test_open_lines_tiny_object_and_empty():
    inbox, fake = make()
    await inbox.ensure_bucket()
    fake.buckets["inbox"]["one"] = b"x"
    fake.buckets["inbox"]["none"] = b""
    assert await lines(inbox, "one") == ["x"]
    assert await lines(inbox, "none") == []


async def test_open_lines_missing_raises_on_first_iteration():
    inbox, _ = make()
    await inbox.ensure_bucket()
    with pytest.raises(ObjectNotFound):
        await lines(inbox, "nope")


async def test_delete_missing_key_is_ok():
    inbox, _ = make()
    await inbox.ensure_bucket()
    await inbox.delete("nope")


async def test_list_objects_pages_and_copy_from_other_bucket():
    inbox, fake = make()
    fake.buckets["cdn"] = {f"logs/{i}": f"line{i}\n".encode() for i in range(5)}
    fake.buckets["cdn"]["other/x"] = b"x"
    found = await inbox.list_objects("logs/", bucket="cdn")
    assert [f["key"] for f in found] == [f"logs/{i}" for i in range(5)]
    sha, size = await inbox.copy_from("cdn", "logs/2", "site/cdn/2026-10-17/a.log")
    assert sha == hashlib.sha256(b"line2\n").hexdigest() and size == 6
    assert fake.buckets["inbox"]["site/cdn/2026-10-17/a.log"] == b"line2\n"


def test_get_inbox_returns_s3_inbox():
    get_inbox.cache_clear()
    assert isinstance(get_inbox(), S3Inbox)
    get_inbox.cache_clear()
