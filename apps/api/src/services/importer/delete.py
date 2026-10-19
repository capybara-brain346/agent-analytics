from dataclasses import dataclass

from psycopg import AsyncConnection

from src.logger import get_logger
from src.models.domain import Lane, SourceType
from src.store import db, events, import_files, locks, views
from src.store.inbox import Inbox, get_inbox

log = get_logger(__name__)


class ImportNotFound(Exception):
    pass


class DeleteBlocked(Exception):
    # The text is the reason for a 409.
    pass


@dataclass(frozen=True)
class DeleteResult:
    file_id: str
    site_id: str
    events_deleted: int
    files_reimported: list[str]


async def _partners(conn: AsyncConnection, file: dict) -> tuple[list[str], list[str]]:
    # A paired row holds one line of a CDN file and one line of an origin file. It goes with
    # either file, so the partner files are read again to restore their own lines.
    # Returns (files to read again, CDN files whose rows go before the new read).
    site_id, file_id = file["site_id"], str(file["id"])
    if file["source"] == SourceType.CDN:
        return await import_files.origin_partners(conn, site_id, file_id), []

    # A CDN partner is read again from the start, like force_reimport: its rows go, and the
    # other origin files it paired with are read again too.
    cdn_ids = await import_files.cdn_partners(conn, site_id, file_id)
    ids = []
    for cdn_id in cdn_ids:
        ids += [cdn_id, *await import_files.origin_partners(conn, site_id, cdn_id)]
    return sorted({i for i in ids if i != file_id}), cdn_ids


async def delete_import(file_id: str, inbox: Inbox | None = None) -> DeleteResult:
    # One transaction under the site's fast-lane lock: no import, pairing or views step of the
    # site runs at the same time, and readers see the old state or the new one, never a mix.
    inbox = inbox or get_inbox()
    async with db.connection() as conn:
        file = await import_files.get_file(conn, file_id)
        if file is None:
            raise ImportNotFound(file_id)

        site_id = file["site_id"]
        if not await locks.try_site_lane_xact_lock(conn, site_id, Lane.FAST):
            raise DeleteBlocked("A pipeline run of this site is active. Try again in a minute.")

        file = await import_files.get_file(conn, file_id)
        if file["status"] == "importing":
            raise DeleteBlocked("The file is importing. Try again when the import ends.")

        reread, cdn_ids = await _partners(conn, file)
        deleted = await events.delete_file_rows(conn, site_id, file_id)
        for cdn_id in cdn_ids:
            await events.delete_file_events(conn, site_id, cdn_id)
        if reread and not await import_files.reset_files(conn, reread):
            raise DeleteBlocked(
                "A paired file cannot be read again (cleanup removed its raw file), "
                "so its lines would be lost. Nothing was deleted."
            )

        await import_files.delete_file(conn, file_id)
        await views.reset_site(conn, site_id)

    # After the commit: a failed object delete leaves only an orphan object, never a lost row.
    if file["object_deleted_at"] is None:
        try:
            await inbox.delete(file["object_key"])
        except Exception as exc:
            log.warning(
                "inbox object not deleted",
                extra={"site_id": site_id, "key": file["object_key"], "error": repr(exc)},
            )
    return DeleteResult(str(file_id), site_id, deleted, reread)
