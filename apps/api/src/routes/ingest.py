from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from src.config import get_settings
from src.models.api import IngestAccepted
from src.models.domain import FilePriority
from src.routes.auth import bearer
from src.services import ingest
from src.services.site_config import SiteConfig, SiteNotFound, load_site_config
from src.store import db, quota
from src.store.inbox import Inbox, get_inbox

router = APIRouter(tags=["ingest"])


def inbox_dependency() -> Inbox:
    return get_inbox()


def load_site(site: str) -> SiteConfig:
    try:
        return load_site_config(site)
    except SiteNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown site: {site}") from None


def source_for(config: SiteConfig, source: str | None) -> str:
    try:
        return ingest.resolve_source(config, source)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None


def declared_length(request: Request) -> int | None:
    value = request.headers.get("content-length", "")
    return int(value) if value.isdigit() else None


async def store_body(
    request: Request,
    config: SiteConfig,
    source: str,
    inbox: Inbox,
    priority: FilePriority,
    entry: str,
    max_bytes: int,
) -> tuple[str, bool]:
    length = declared_length(request)
    if length is not None and length > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Body is too large")
    try:
        return await ingest.accept_chunk(
            config.site_id, source, request.stream(), priority, entry, inbox, max_bytes
        )
    except ingest.PayloadTooLarge:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Body is too large") from None
    except ingest.EmptyBody:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Body is empty") from None


@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"model": IngestAccepted, "description": "Duplicate chunk, already stored"}},
)
async def ingest_chunk(
    request: Request,
    response: Response,
    site: Annotated[str, Query()],
    inbox: Annotated[Inbox, Depends(inbox_dependency)],
    source: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> IngestAccepted:
    # An unknown site and a bad token give the same answer: the route does not leak site ids.
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, "Bad token", headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        config = load_site_config(site)
    except SiteNotFound:
        raise unauthorized from None
    if not await ingest.check_site_token(site, bearer(authorization)):
        raise unauthorized
    source = source_for(config, source)
    max_bytes = get_settings().ingest_max_bytes
    if not await ingest.check_rate_limit(site, declared_length(request)):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit or quota reached",
            headers={"Retry-After": "60"},
        )
    # The byte quota is read from Postgres, so all API replicas share it. The request rate window
    # above stays in memory: with N replicas the real limit is up to N times the setting.
    async with db.connection() as conn:
        used = await quota.bytes_received_last_day(conn, site, datetime.now(UTC))
    if used + (declared_length(request) or 0) > get_settings().ingest_bytes_per_day:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Rate limit or quota reached",
            headers={"Retry-After": "3600"},
        )
    file_id, duplicate = await store_body(
        request, config, source, inbox, FilePriority.LIVE, "ingest", max_bytes
    )
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return IngestAccepted(file_id=file_id, duplicate=duplicate)
