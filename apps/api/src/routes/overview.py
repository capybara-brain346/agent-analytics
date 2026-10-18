from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Query

from src.models.api import (
    CLASS_NAMES,
    PATTERN_NAMES,
    AlertOut,
    ClassRow,
    Coverage,
    Freshness,
    KeyNumber,
    Overview,
    RecommendationBrief,
    TopAgent,
    TopPage,
    TrendPoint,
)
from src.routes.params import Conn, ScopeDep, pct
from src.services import site_config
from src.store import queries

router = APIRouter(prefix="/overview", tags=["overview"])

CONFIDENCES = ("high", "medium", "low")
CANNOT_SEE = ["task completion", "page content", "clicks and form steps"]
PARTIAL = ["browser traffic without an edge bot signal is Unknown"]


def key_number(value: float | int | None, previous: float | int | None, unit: str) -> KeyNumber:
    change = None
    if value is not None and previous:
        change = round(100.0 * (value - previous) / previous, 2)
    return KeyNumber(value=value, previous=previous, change_pct=change, unit=unit)


def key_numbers(cur: dict, prev: dict) -> dict[str, KeyNumber]:
    def rates(n: dict) -> dict:
        total = n.get("total") or 0
        return {
            "total_requests": total,
            "ai_or_automated_share": pct(n.get("agent_requests"), total),
            "distinct_agents": n.get("distinct_agents") or 0,
            "error_rate": pct(n.get("errors"), total),
            "denial_rate": pct(n.get("denied"), total),
        }

    c, p = rates(cur), rates(prev)
    units = {
        "total_requests": "requests",
        "ai_or_automated_share": "percent",
        "distinct_agents": "agents",
        "error_rate": "percent",
        "denial_rate": "percent",
    }
    return {k: key_number(c[k], p[k], units[k]) for k in units}


def banner(fresh: dict, alerts: list[dict], site_id: str) -> Freshness:
    up_to = fresh["data_up_to"]
    run = fresh["latest_run"] or {}
    at = up_to.strftime("%H:%M") if up_to else "unknown"
    kinds = {a["kind"] for a in alerts}
    if "failed_runs" in kinds:
        since = run.get("started_at")
        state, text = (
            "alert_failing",
            "ALERT: pipeline failing" + (f" since {since:%H:%M}" if since else ""),
        )
    elif "no_data" in kinds:
        a = next(a for a in alerts if a["kind"] == "no_data")
        state, text = (
            "alert_no_data",
            f"ALERT: no new logs from {site_id} since {a['raised_at']:%H:%M}",
        )
    elif run.get("status") == "running":
        state, text = "updating", f"Updating... (data up to {at})"
    elif run.get("status") == "failed":
        step = run.get("failed_step") or "unknown step"
        state, text = "last_run_failed", f"Data up to {at} - last run failed at {step}"
    elif not run and not up_to:
        state, text = "no_runs", "No pipeline run yet"
    else:
        state, text = "ok", f"Data up to {at}"
    return Freshness(
        state=state,
        text=text,
        data_up_to=up_to,
        last_import_at=fresh["last_import_at"],
        latest_run_id=run.get("id"),
        failed_step=run.get("failed_step") if run.get("status") == "failed" else None,
        consecutive_failures=fresh["consecutive_failures"],
    )


@router.get("", response_model=Overview)
async def get_overview(
    conn: Conn,
    scope: ScopeDep,
    bucket: Annotated[str, Query(pattern="^(hour|day)$")] = "hour",
) -> Overview:
    f = scope.filters()
    cur = await queries.overview_numbers(conn, f)
    prev = await queries.overview_numbers(conn, queries.previous_window(f))
    total = cur.get("total") or 0

    cells: dict[int, dict[str, int]] = {}
    unclassified = 0
    for r in await queries.traffic_by_class_confidence(conn, f):
        if r["traffic_class"] is None:
            unclassified += r["requests"]
            continue
        row = cells.setdefault(r["traffic_class"], dict.fromkeys(CONFIDENCES, 0))
        row[r["confidence"] or "low"] += r["requests"]
    classes = scope.classes or list(CLASS_NAMES)
    by_class = [
        ClassRow(
            traffic_class=c,
            name=CLASS_NAMES[c],
            requests=sum(cells.get(c, {}).values()),
            share_pct=pct(sum(cells.get(c, {}).values()), total) or 0.0,
            high=cells.get(c, {}).get("high", 0),
            medium=cells.get(c, {}).get("medium", 0),
            low=cells.get(c, {}).get("low", 0),
        )
        for c in classes
    ]

    points: dict = {}
    for r in await queries.trend(conn, f, bucket):
        p = points.setdefault(r["bucket"], {"total": 0, "by_class": {}})
        p["total"] += r["requests"]
        key = str(r["traffic_class"]) if r["traffic_class"] else "unclassified"
        p["by_class"][key] = p["by_class"].get(key, 0) + r["requests"]
    trend = [TrendPoint(bucket=b, **v) for b, v in sorted(points.items())]

    fresh = await queries.freshness(conn, scope.site_id)
    alerts = await queries.open_alerts(conn, scope.site_id)

    cfg = site_config.load_site_config(scope.site_id)
    sources = await queries.source_counts(conn, replace(f, classes=[]))
    paired_share = None
    if cfg.pairs_sources:
        paired_share = pct(
            sources.get("paired", 0), sources.get("paired", 0) + sources.get("origin", 0)
        )
    class6 = cells.get(6, {})
    unknown_share = pct(sum(class6.values()), total) if total else None

    run = await queries.latest_run(conn, scope.site_id)
    top_recs: list[RecommendationBrief] = []
    if run:
        for r in await queries.list_recommendations(conn, run["id"]):
            if r["change"] == "gone" or len(top_recs) == 3:
                continue
            top_recs.append(
                RecommendationBrief(
                    id=r["id"],
                    rank=r["rank"],
                    target=r["target"],
                    pattern=r["pattern"],
                    pattern_name=PATTERN_NAMES.get(r["pattern"], r["pattern"]),
                    score=r["score"],
                    confidence=r["confidence"],
                    change=r["change"],
                )
            )

    return Overview(
        window=scope.window(),
        empty=total == 0,
        freshness=banner(fresh, alerts, scope.site_id),
        key_numbers=key_numbers(cur, prev),
        traffic_by_class=by_class,
        unclassified_requests=unclassified,
        trend=trend,
        top_agents=[TopAgent(**r) for r in await queries.top_agents(conn, f, 5)],
        top_pages=[TopPage(**r) for r in await queries.top_pages(conn, f, 10)],
        top_recommendations=top_recs,
        coverage=Coverage(
            sources_configured=[s.value for s in cfg.sources],
            sources_present=sorted(sources),
            paired_share_pct=paired_share,
            unknown_share_pct=unknown_share,
            cannot_see=CANNOT_SEE,
            partial=PARTIAL,
        ),
        open_alerts_count=len(alerts),
        open_alerts=[AlertOut(**a) for a in alerts],
    )
