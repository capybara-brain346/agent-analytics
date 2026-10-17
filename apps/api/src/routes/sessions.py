from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from src.config import get_settings
from src.models.api import (
    CLASS_NAMES,
    Gap,
    LabeledText,
    Paged,
    SessionDetail,
    SessionRow,
    SessionStep,
)
from src.routes.params import Conn, PagingDep, ScopeDep, Site, not_found, utcnow
from src.services import site_config
from src.store import queries

router = APIRouter(prefix="/sessions", tags=["sessions"])


def session_row(r: dict, now: datetime) -> SessionRow:
    age = int((now - r["last_seen"]).total_seconds()) if r["in_progress"] else None
    return SessionRow(
        session_id=r["session_id"],
        client_key=r["client_key"],
        agent=r["claimed_agent"],
        traffic_class=r["traffic_class"],
        class_name=CLASS_NAMES.get(r["traffic_class"]),
        confidence=r["confidence"],
        started=r["started"],
        last_seen=r["last_seen"],
        state="in_progress" if r["in_progress"] else "closed",
        in_progress=r["in_progress"],
        last_event_age_seconds=max(age, 0) if age is not None else None,
        requests=r["requests"],
        distinct_pages=r["distinct_pages"],
        has_retry=r["has_retry"],
        has_loop=r["has_loop"],
        reached_conversion=r["reached_conversion"],
        journeys_reached={k: int(v) for k, v in (r["journeys_reached"] or {}).items()},
    )


@router.get("", response_model=Paged[SessionRow])
async def list_sessions(
    conn: Conn,
    scope: ScopeDep,
    paging: PagingDep,
    agent: str | None = None,
    confidence: Annotated[str | None, Query(pattern="^(high|medium|low)$")] = None,
    state: Annotated[str | None, Query(pattern="^(in_progress|closed)$")] = None,
    has_retry: bool | None = None,
    has_loop: bool | None = None,
    reached_conversion: bool | None = None,
    journey: str | None = None,
    reached_step: Annotated[int | None, Query(ge=1)] = None,
    client_key: str | None = None,
) -> Paged[SessionRow]:
    if journey and journey not in {
        j.id for j in site_config.load_site_config(scope.site_id).journeys
    }:
        raise not_found("journey", journey)
    f = scope.filters(agent=agent, confidence=confidence, client_key=client_key)
    rows, total = await queries.list_sessions(
        conn,
        f,
        paging.limit,
        paging.offset,
        in_progress=None if state is None else state == "in_progress",
        has_retry=has_retry,
        has_loop=has_loop,
        reached_conversion=reached_conversion,
        journey=journey,
        reached_step=reached_step,
    )
    now = utcnow()
    return Paged(items=[session_row(r, now) for r in rows], page=paging.info(total))


def confidence_reason(r: dict) -> str:
    if r["shared_ip"]:
        return "Shared IP: one address may hold more than one agent"
    verdict = (r.get("verdict_row") or {}).get("verdict")
    if r["confidence"] == "high":
        return "Verified identity, IP not shared"
    if r["confidence"] == "medium":
        return f"Identity {verdict or 'unverified'}, IP not shared"
    return "Agent client or unknown class"


def build_steps(events: list[dict], key_pages: set[str], conv_pages: set[str]) -> list[SessionStep]:
    settings = get_settings()
    steps, prev, seen = [], None, {}
    for e in events:
        flags = []
        if (
            prev
            and prev["path"] == e["path"]
            and (prev["status"] or 0) >= 400
            and (e["ts"] - prev["ts"]).total_seconds() <= settings.retry_window_seconds
        ):
            flags.append("retry")
        seen[e["path"]] = seen.get(e["path"], 0) + 1
        if seen[e["path"]] >= settings.loop_repeat_count:
            flags.append("loop")
        if e["path"] in key_pages:
            flags.append("key_page")
        if e["path"] in conv_pages:
            flags.append("conversion_page")
        steps.append(
            SessionStep(
                seq=e["seq"],
                event_id=e["id"],
                ts=e["ts"],
                path=e["path"],
                method=e["method"],
                status=e["status"],
                delta_seconds=(e["ts"] - prev["ts"]).total_seconds() if prev else None,
                flags=flags,
            )
        )
        prev = e
    return steps


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(conn: Conn, site: Site, session_id: str) -> SessionDetail:
    r = await queries.get_session(conn, site, session_id)
    if r is None:
        raise not_found("session", session_id)
    cfg = site_config.load_site_config(site)
    now = utcnow()
    row = session_row(r, now)
    gaps = [Gap(text=g, label="unknown") for g in r["gaps"]]
    if r["shared_ip"] and not any("shared" in g.text.lower() for g in gaps):
        gaps.append(Gap(text="shared IP: may contain more than one agent", label="inferred"))
    grouping = (
        f"These {r['requests']} requests likely form one visit (same client, no gap over "
        f"{get_settings().session_gap_minutes} min)"
    )
    state_note = (
        f"In progress (last event {row.last_event_age_seconds // 60} min ago, can still grow)"
        if r["in_progress"]
        else "Closed"
    )
    return SessionDetail(
        session=row,
        facts={
            "state": state_note,
            "requests": r["requests"],
            "distinct_pages": r["distinct_pages"],
            "status_counts": r["status_counts"],
            "has_retry": r["has_retry"],
            "has_loop": r["has_loop"],
            "retries": r["retries"],
            "key_pages_visited": r["key_pages_visited"],
            "reached_conversion": r["reached_conversion"],
            "journeys_reached": row.journeys_reached,
        },
        grouping=LabeledText(text=grouping, label="inferred"),
        confidence_reason=LabeledText(text=confidence_reason(r), label="inferred"),
        steps=build_steps(r["events"], set(cfg.key_pages), set(cfg.conversion_pages)),
        outcome=LabeledText(
            text="Task outcome: Unknown - logs cannot show completion", label="unknown"
        ),
        gaps=gaps,
        recommendations=r["recommendations"],
    )
