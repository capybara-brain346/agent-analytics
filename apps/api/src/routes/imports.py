from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel

from src.config import get_settings
from src.models.api import IngestAccepted
from src.models.domain import FilePriority
from src.routes.ingest import inbox_dependency, load_site, source_for, store_body
from src.store import db, import_files
from src.store.inbox import Inbox

router = APIRouter(prefix="/imports", tags=["imports"])


class OverlapWarning(BaseModel):
    file_id: str
    message: str


class ImportFile(BaseModel):
    id: str
    site_id: str
    source: str
    entry: str
    priority: str
    status: str
    size_bytes: int
    received_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    lines_total: int
    lines_imported: int
    lines_rejected: int
    lines_duplicate: int
    rejects_count: int
    min_ts: datetime | None
    max_ts: datetime | None
    error: str | None
    delete_on: datetime | None
    overlap_warning: OverlapWarning | None


class ImportList(BaseModel):
    items: list[ImportFile]
    total: int
    limit: int
    offset: int


async def _to_model(conn, row: dict, retention_days: int) -> ImportFile:
    overlap = None
    if row["status"] == "success" and row["min_ts"] is not None:
        others = await import_files.overlapping_files(conn, row["site_id"], row["id"])
        if others:
            ids = ", ".join(str(o["id"]) for o in others[:3])
            overlap = OverlapWarning(
                file_id=str(others[0]["id"]),
                message=f"Time range overlaps file {ids}: possible double count",
            )
    delete_on = None
    if row["status"] == "success" and row["finished_at"] and row["object_deleted_at"] is None:
        delete_on = row["finished_at"] + timedelta(days=retention_days)
    return ImportFile(
        id=str(row["id"]),
        site_id=row["site_id"],
        source=row["source"],
        entry=row["entry"],
        priority=row["priority"],
        status=row["status"],
        size_bytes=row["size_bytes"],
        received_at=row["received_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        lines_total=row["lines_total"],
        lines_imported=row["lines_imported"],
        lines_rejected=row["lines_rejected"],
        lines_duplicate=row["lines_duplicate"],
        rejects_count=row["lines_rejected"],
        min_ts=row["min_ts"],
        max_ts=row["max_ts"],
        error=row["error"],
        delete_on=delete_on,
        overlap_warning=overlap,
    )


@router.get("")
async def list_imports(
    site: Annotated[str | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ImportList:
    if site is not None:
        load_site(site)
    retention = get_settings().raw_retention_days
    async with db.connection() as conn:
        rows = await import_files.list_files(conn, site, status_filter, limit, offset)
        total = await import_files.count_files(conn, site, status_filter)
        items = [await _to_model(conn, row, retention) for row in rows]
    return ImportList(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"model": IngestAccepted, "description": "Duplicate file, already stored"}},
)
async def upload(
    request: Request,
    response: Response,
    site: Annotated[str, Query()],
    inbox: Annotated[Inbox, Depends(inbox_dependency)],
    source: Annotated[str | None, Query()] = None,
) -> IngestAccepted:
    config = load_site(site)
    source = source_for(config, source)
    file_id, duplicate = await store_body(
        request,
        config,
        source,
        inbox,
        FilePriority.BACKFILL,
        "upload",
        get_settings().upload_max_bytes,
    )
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return IngestAccepted(file_id=file_id, duplicate=duplicate)
