from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query
from psycopg import AsyncConnection

from src.models.api import PageInfo, Window
from src.services import site_config
from src.store import db
from src.store.queries import Filters


def utcnow() -> datetime:
    return datetime.now(UTC)


def error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def not_found(what: str, ident: object) -> HTTPException:
    return error(404, f"{what}_not_found", f"No {what.replace('_', ' ')} with id {ident!r}")


async def get_conn() -> AsyncIterator[AsyncConnection]:
    async with db.connection() as conn:
        yield conn


Conn = Annotated[AsyncConnection, Depends(get_conn)]


def resolve_site(site: str | None) -> str:
    sites = site_config.list_sites()
    if site is None:
        if len(sites) == 1:
            return sites[0]
        raise error(422, "site_required", f"Query parameter 'site' is required. Sites: {sites}")
    if site not in sites:
        raise error(404, "site_not_found", f"Unknown site {site!r}. Sites: {sites}")
    return site


def site_param(site: str | None = None) -> str:
    return resolve_site(site)


Site = Annotated[str, Depends(site_param)]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True)
class Scope:
    site_id: str
    start: datetime
    end: datetime
    classes: list[int]

    def filters(self, **extra: Any) -> Filters:
        return Filters(self.site_id, self.start, self.end, self.classes, **extra)

    def window(self) -> Window:
        return Window(site=self.site_id, start=self.start, end=self.end, classes=self.classes)


def scope_param(
    site: Annotated[
        str | None, Query(description="Site id. Optional when one site exists.")
    ] = None,
    from_: Annotated[datetime | None, Query(alias="from", description="ISO 8601, UTC")] = None,
    to: Annotated[datetime | None, Query(description="ISO 8601, UTC. Default: now")] = None,
    traffic_class: Annotated[
        list[str] | None, Query(alias="class", description="Class 1..6, repeat or comma list")
    ] = None,
) -> Scope:
    site_id = resolve_site(site)
    end = _utc(to) if to else utcnow()
    start = _utc(from_) if from_ else end - timedelta(hours=24)
    if start >= end:
        raise error(422, "bad_range", "'from' must be earlier than 'to'")
    classes: list[int] = []
    for raw in traffic_class or []:
        for token in raw.split(","):
            if not token.strip().isdigit() or not 1 <= int(token) <= 6:
                raise error(422, "bad_class", f"class must be 1..6, got {token!r}")
            classes.append(int(token))
    return Scope(site_id, start, end, sorted(set(classes)))


ScopeDep = Annotated[Scope, Depends(scope_param)]


@dataclass(frozen=True)
class Paging:
    limit: int
    offset: int

    def info(self, total: int) -> PageInfo:
        nxt = self.offset + self.limit
        return PageInfo(
            limit=self.limit,
            offset=self.offset,
            total=total,
            next_offset=nxt if nxt < total else None,
        )


def paging_param(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Paging:
    return Paging(limit, offset)


PagingDep = Annotated[Paging, Depends(paging_param)]


def pct(part: int | float | None, whole: int | float | None) -> float | None:
    if not whole:
        return None
    return round(100.0 * (part or 0) / whole, 2)
