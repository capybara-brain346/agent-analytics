from typing import Annotated

from fastapi import APIRouter, Query

from src.models.api import (
    CLASS_NAMES,
    AgentDetail,
    AgentRow,
    ClientKeyRow,
    VerdictRow,
)
from src.routes.params import Conn, ScopeDep, not_found, utcnow
from src.routes.sessions import session_row
from src.services import registry
from src.store import queries

router = APIRouter(prefix="/agents", tags=["agents"])

VERIFICATIONS = "^(VERIFIED|CLAIMED|UNVERIFIED|SPOOFED|UNKNOWN)$"


def vendors() -> dict[str, str]:
    _, entries = registry.load_registry()
    return {e.id: e.vendor for e in entries}


def verification_note(name: str, verification: str | None) -> str:
    if verification == "VERIFIED":
        return f"Verified: traffic matches the vendor's published list for {name}"
    if verification == "SPOOFED":
        return f"Claims to be {name}, but the source does not match: spoofed"
    return f"Claims to be {name}, unverified"


def agent_row(r: dict, vendor_map: dict[str, str]) -> AgentRow:
    name = r["claimed_agent"]
    return AgentRow(
        agent_id=name,
        name=name,
        vendor=vendor_map.get(name),
        traffic_class=r["traffic_class"],
        class_name=CLASS_NAMES.get(r["traffic_class"], "Unknown"),
        verification=r["verification"],
        verification_note=verification_note(name, r["verification"]),
        confidence=r["confidence"],
        first_seen=r["first_seen"],
        last_seen=r["last_seen"],
        requests=r["requests"],
        sessions=r.get("sessions", 0),
        distinct_pages=r.get("distinct_pages", 0),
        common_paths=r.get("common_paths", []),
    )


def verdict_row(v: dict, site: str) -> VerdictRow:
    return VerdictRow(
        **{k: v[k] for k in VerdictRow.model_fields if k != "events_link" and k in v},
        events_link=f"/api/events?site={site}&verdict_id={v['id']}",
    )


@router.get("", response_model=list[AgentRow])
async def list_agents(
    conn: Conn,
    scope: ScopeDep,
    verification: Annotated[str | None, Query(pattern=VERIFICATIONS)] = None,
    q: Annotated[str | None, Query(description="Agent name contains")] = None,
) -> list[AgentRow]:
    rows = await queries.list_agents(conn, scope.filters(), verification, q)
    vm = vendors()
    return [agent_row(r, vm) for r in rows]


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent(conn: Conn, scope: ScopeDep, agent_id: str) -> AgentDetail:
    f = scope.filters()
    data = await queries.get_agent(conn, f, agent_id)
    if data is None:
        raise not_found("agent", agent_id)
    # Header uses the latest hourly row; totals use the range (class filter is ignored here).
    rows = [
        r
        for r in await queries.list_agents(conn, scope.filters())
        if r["claimed_agent"] == agent_id
    ]
    latest = data["latest"] or {}
    if rows:
        head = agent_row(rows[0], vendors())
    else:
        head = agent_row(
            {
                "claimed_agent": agent_id,
                "traffic_class": latest.get("traffic_class") or 6,
                "verification": latest.get("verification"),
                "confidence": latest.get("confidence"),
                "first_seen": latest.get("first_seen"),
                "last_seen": latest.get("last_seen"),
                "requests": 0,
            },
            vendors(),
        )
    history = data["verdict_history"]
    current = next(
        (v for v in history if v["traffic_class"] is not None), history[0] if history else {}
    )
    why = {
        "rule_id": current.get("rule_id"),
        "rule_version": current.get("rule_version"),
        "registry_version": current.get("registry_version"),
        "inputs": {
            "verdict": current.get("verdict"),
            "registry_category": current.get("registry_category"),
            "ua_type": current.get("ua_type"),
            "edge_signal": current.get("edge_signal"),
        },
        "evidence": current.get("class_evidence"),
        "label": "inferred",
    }
    seen: dict[str, ClientKeyRow] = {}
    for v in history:
        seen.setdefault(
            v["client_key"],
            ClientKeyRow(
                client_key=v["client_key"],
                user_agent=v["user_agent"],
                client_ip=v["client_ip"],
                shared_ip=v["shared_ip"],
            ),
        )
    now = utcnow()
    return AgentDetail(
        agent=head,
        why_this_class=why,
        verdict_history=[verdict_row(v, scope.site_id) for v in history],
        client_keys=list(seen.values()),
        activity=data["activity"],
        top_paths=data["top_paths"],
        status_mix=data["status_mix"],
        sessions=[session_row(s, now) for s in data["sessions"]],
    )
