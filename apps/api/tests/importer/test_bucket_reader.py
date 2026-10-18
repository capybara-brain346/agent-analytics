from datetime import timedelta

from src.services.importer.bucket_reader import (
    BucketReader,
    BucketTarget,
    targets_from_site_files,
)
from src.store import import_files
from tests.factories import NOW
from tests.fakes import MemoryInbox

TARGET = BucketTarget(site_id="example", source="cdn", bucket="cdn-logs", prefix="logs/")


class FakeBucketInbox(MemoryInbox):
    def __init__(self, objects: dict[str, tuple[bytes, object]]):
        super().__init__()
        self.source = objects

    async def list_objects(self, prefix="", bucket=None):
        return [
            {"key": k, "size": len(d), "last_modified": m, "etag": str(len(d))}
            for k, (d, m) in self.source.items()
            if k.startswith(prefix)
        ]

    async def copy_from(self, bucket, key, dest_key=None):
        sha, size = self.put_bytes(dest_key or key, self.source[key][0])
        return sha, size


async def test_copies_new_objects_and_skips_known(conn, settings):
    inbox = FakeBucketInbox(
        {
            "logs/a.json": (b"line a\n", NOW),
            "logs/b.json": (b"line b\n", NOW),
            "other/c.json": (b"nope\n", NOW),
            "logs/old.json": (b"old\n", NOW - timedelta(days=30)),
            "logs/empty.json": (b"", NOW),
        }
    )
    reader = BucketReader(inbox)
    counts = await reader.read_new(conn, TARGET, now=NOW)
    assert counts == {"objects_new": 2, "objects_duplicate": 0, "objects_skipped": 2}
    files = await import_files.list_files(conn, "example")
    assert {f["entry"] for f in files} == {"bucket"}
    assert {f["priority"] for f in files} == {"live"}
    assert {f["source"] for f in files} == {"cdn"}
    assert len(inbox.objects) == 2
    again = await reader.read_new(conn, TARGET, now=NOW)
    assert again["objects_new"] == 0


async def test_same_content_in_new_reader_is_duplicate_and_copy_deleted(conn, settings):
    first = FakeBucketInbox({"logs/a.json": (b"line a\n", NOW)})
    await BucketReader(first).read_new(conn, TARGET, now=NOW)
    inbox = FakeBucketInbox({"logs/renamed.json": first.source["logs/a.json"]})
    counts = await BucketReader(inbox).read_new(conn, TARGET, now=NOW)
    assert counts["objects_duplicate"] == 1
    assert inbox.objects == {}


def test_targets_from_site_files(config_dir, settings):
    (config_dir / "sites" / "withbucket.yaml").write_text(
        "site_id: withbucket\nsources: [cdn]\ncdn_bucket: {bucket: b1, prefix: p/}\n"
    )
    assert targets_from_site_files() == [BucketTarget("withbucket", "cdn", "b1", "p/")]
