import gzip

import pytest

from src.config import Settings
from src.store.inbox import MAX_LINE_CHARS, ObjectTooLarge, S3Inbox
from tests.ingest.fake_s3 import FakeS3


def make(**settings) -> S3Inbox:
    fake = FakeS3(("inbox",))
    return S3Inbox(Settings(s3_bucket="inbox", **settings), client=fake), fake


async def lines(inbox, key):
    return [line async for line in inbox.open_lines(key)]


async def test_line_without_newline_is_cut_and_rest_skipped():
    inbox, fake = make(ingest_chunk_bytes=4096)
    big = b"A" * (5 * MAX_LINE_CHARS)
    fake.buckets["inbox"]["k"] = gzip.compress(b"ok\n" + big + b"\nafter\n" + big)
    got = await lines(inbox, "k")
    assert [len(x) for x in got] == [2, MAX_LINE_CHARS + 1, 5, MAX_LINE_CHARS + 1]
    assert got[2] == "after"


async def test_plain_long_line_is_cut():
    inbox, fake = make()
    fake.buckets["inbox"]["k"] = b"A" * (3 * MAX_LINE_CHARS) + b"\nz\n"
    assert [len(x) for x in await lines(inbox, "k")] == [MAX_LINE_CHARS + 1, 1]


async def test_decompressed_size_is_capped():
    inbox, fake = make(max_decompressed_bytes=1_000_000)
    fake.buckets["inbox"]["k"] = gzip.compress((b"A" * 99 + b"\n") * 100_000)
    with pytest.raises(ObjectTooLarge):
        await lines(inbox, "k")


async def test_multi_member_gzip_still_works():
    inbox, fake = make()
    fake.buckets["inbox"]["k"] = gzip.compress(b"a\nb\n") + gzip.compress(b"c\n")
    assert await lines(inbox, "k") == ["a", "b", "c"]
