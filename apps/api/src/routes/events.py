from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from src.models.api import CLASS_NAMES, EventDetail, EventRow, Paged, SessionLink
from src.routes.agents import verdict_row
from src.routes.params import Conn, PagingDep, ScopeDep, Site, error, not_found
from src.store import queries

router = APIRouter(prefix="/events", tags=["events"])

REQUEST_FIELDS = (
    "ts host method path status bytes_sent response_time_ms referrer user_agent client_ip "
    "client_key edge_signal"
).split()
SOURCE_FIELDS = (
    "source pair_state edge_status origin_status request_id edge_request_id cdn_bypass "
    "file_id line_no"
).split()


@router.get("", response_model=Paged[EventRow])
async def list_events(
    conn: Conn,
    scope: ScopeDep,
    paging: PagingDep,
    agent: str | None = None,
    path: Annotated[str | None, Query(description="Path contains")] = None,
    status: Annotated[str | None, Query(description="403, 4xx or a comma list")] = None,
    verdict: Annotated[
        str | None, Query(pattern="^(VERIFIED|CLAIMED|UNVERIFIED|SPOOFED|UNKNOWN)$")
    ] = None,
    verdict_id: int | None = None,
    confidence: Annotated[str | None, Query(pattern="^(high|medium|low)$")] = None,
    client_key: str | None = None,
    session: str | None = None,
    source: Annotated[str | None, Query(pattern="^(origin|cdn|paired)$")] = None,
    import_file: str | None = None,
) -> Paged[EventRow]:
    if status and not queries.valid_status(status):
        raise error(422, "bad_status", f"status must look like 403, 4xx or 403,429, got {status!r}")
    if import_file:
        try:
            UUID(import_file)
        except ValueError as exc:
            raise error(422, "bad_import_file", "import_file must be a UUID") from exc
    f = scope.filters(
        agent=agent,
        verdict=verdict,
        verdict_id=verdict_id,
        confidence=confidence,
        status=status,
        path_contains=path,
        client_key=client_key,
        session_id=session,
        source=source,
        file_id=import_file,
    )
    rows, total = await queries.list_events(conn, f, paging.limit, paging.offset)
    items = [EventRow(**r, class_name=CLASS_NAMES.get(r["traffic_class"])) for r in rows]
    return Paged(items=items, page=paging.info(total))


@router.get("/{event_id}", response_model=EventDetail)
async def get_event(conn: Conn, site: Site, event_id: int) -> EventDetail:
    e = await queries.get_event(conn, site, event_id)
    if e is None:
        raise not_found("event", event_id)
    v = e["verdict_row"]
    link = e["session"]
    return EventDetail(
        id=e["id"],
        request={k: e[k] for k in REQUEST_FIELDS},
        source={k: e[k] for k in SOURCE_FIELDS},
        verdict=verdict_row(v, site) if v else None,
        classification=(
            {
                "traffic_class": v["traffic_class"],
                "class_name": CLASS_NAMES.get(v["traffic_class"]),
                "confidence": v["confidence"],
                "rule_id": v["rule_id"],
                "rule_version": v["rule_version"],
                "inputs": {
                    "verdict": v["verdict"],
                    "registry_category": v["registry_category"],
                    "ua_type": v["ua_type"],
                    "edge_signal": v["edge_signal"],
                },
                "evidence": v["class_evidence"],
                "label": "inferred",
            }
            if v and v["traffic_class"] is not None
            else None
        ),
        session=SessionLink(session_id=link["session_id"], position=link["seq"], of=link["total"])
        if link
        else None,
        import_file=e["import_file"],
        recommendations=e["recommendations"],
    )
