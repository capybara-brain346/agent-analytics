import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from psycopg import AsyncConnection

from src.config import get_settings
from src.services.site_config import list_sites, load_site_config
from src.store import import_files, locks


class BucketInbox(Protocol):
    # Implemented by S3Inbox
    async def delete(self, key: str) -> None: ...

    async def list_objects(self, prefix: str = "", bucket: str | None = None) -> list[dict]: ...

    async def copy_from(
        self, bucket: str, key: str, dest_key: str | None = None
    ) -> tuple[str, int]: ...


@dataclass(frozen=True)
class BucketTarget:
    site_id: str
    source: str
    bucket: str
    prefix: str = ""


@dataclass
class BucketReader:
    inbox: BucketInbox

    async def read_new(
        self, conn: AsyncConnection, target: BucketTarget, now: datetime | None = None
    ) -> dict:
        # Copy each object into the inbox. A mark (bucket, key, size, etag) is stored in Postgres
        # after the copy, so a restart or a second worker does not copy the same object again. A
        # copy of known content (same sha256) is a duplicate: insert_new returns None and the
        # copy is deleted.
        # One worker reads a target at a time (advisory lock). Each object is committed alone:
        # an error on object k keeps objects 1..k-1 (copy, file row and mark go together).
        now = now or datetime.now(UTC)
        oldest = now - timedelta(days=get_settings().raw_retention_days)
        counts = {"objects_new": 0, "objects_duplicate": 0, "objects_skipped": 0}
        key = locks.bucket_lock_key(target.site_id, target.bucket, target.prefix)
        async with locks.advisory_lock(conn, key) as got:
            await conn.commit()
            if not got:
                return counts
            listing = await self.inbox.list_objects(target.prefix, target.bucket)
            marks = {
                obj["key"]: f"{target.bucket}/{obj['key']}#{obj['size']}#{obj.get('etag')}"
                for obj in listing
            }
            known = await import_files.known_bucket_marks(
                conn, target.site_id, list(marks.values())
            )
            await conn.commit()
            for obj in listing:
                mark = marks[obj["key"]]
                modified = obj.get("last_modified")
                if mark in known or not obj["size"] or (modified and modified < oldest):
                    counts["objects_skipped"] += 1
                    continue
                await self._copy_one(conn, target, obj["key"], mark, counts)
        return counts

    async def _copy_one(
        self, conn: AsyncConnection, target: BucketTarget, name: str, mark: str, counts: dict
    ) -> None:
        key = f"bucket/{target.site_id}/{uuid.uuid4().hex}"
        sha256, size = await self.inbox.copy_from(target.bucket, name, key)
        try:
            async with conn.transaction():
                file_id = await import_files.insert_new(
                    conn, target.site_id, target.source, key, sha256, size, "live", "bucket"
                )
                await import_files.remember_bucket_mark(conn, target.site_id, mark)
            await conn.commit()
        except BaseException:
            await conn.rollback()
            await self.inbox.delete(key)  # No file row: nothing would ever delete the copy
            raise
        if file_id is None:
            await self.inbox.delete(key)
            counts["objects_duplicate"] += 1
        else:
            counts["objects_new"] += 1


def targets_from_site_files() -> list[BucketTarget]:
    # Site file: cdn_bucket: {bucket: ..., prefix: ..., source: cdn}
    targets = []
    for site_id in list_sites():
        block = load_site_config(site_id).cdn_bucket
        if block is not None:
            targets.append(BucketTarget(site_id, block.source, block.bucket, block.prefix))
    return targets
