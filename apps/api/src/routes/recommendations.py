from typing import Annotated

from fastapi import APIRouter, Query

from src.logger import get_logger
from src.models.api import (
    PATTERN_NAMES,
    EvidenceRef,
    Factor,
    GenerateResult,
    HistoryEntry,
    LabeledText,
    Paged,
    Priority,
    RecommendationBrief,
    RecommendationDetail,
    RecommendationItem,
    RecommendationList,
    RunHeader,
)
from src.routes.params import Conn, PagingDep, Site, error, not_found
from src.store import queries

log = get_logger(__name__)
router = APIRouter(prefix="/recommendations", tags=["recommendations"])

FACTORS = ("impact", "frequency", "severity", "confidence")
WINDOW_PATTERN = r"^\d+[hd]$"


def priority(r: dict) -> Priority:
    values = {
        "impact": r["impact"],
        "frequency": r["frequency"],
        "severity": r["severity"],
        "confidence": float(r["confidence_factor"]),
    }
    reasons = r.get("factor_reasons") or {}
    return Priority(
        score=r["score"],
        formula=(
            f"{float(r['score']):g} = {values['impact']} x {values['frequency']} x "
            f"{values['severity']} x {values['confidence']:.1f}"
        ),
        factors={k: Factor(value=values[k], why=reasons.get(k)) for k in FACTORS},
    )


def item(r: dict) -> RecommendationItem:
    return RecommendationItem(
        id=r["id"],
        run_id=r["run_id"],
        stable_id=r["stable_id"],
        rank=r["rank"],
        change=r["change"],
        pattern=r["pattern"],
        pattern_name=PATTERN_NAMES.get(r["pattern"], r["pattern"]),
        journey_id=r["journey_id"],
        target=r["target"],
        recommended_test=r["recommended_test"],
        priority=priority(r),
        confidence=r["confidence"],
        sessions_count=r["sessions_count"],
        events_count=r["events_count"],
        text_source=r["text_source"],
    )


def brief(r: dict) -> RecommendationBrief:
    return RecommendationBrief(
        id=r["id"],
        rank=r.get("rank"),
        target=r.get("target", ""),
        pattern=r["pattern"],
        pattern_name=PATTERN_NAMES.get(r["pattern"], r["pattern"]),
        score=r["score"],
        confidence=r.get("confidence", ""),
        change=r.get("change"),
    )


def header(run: dict, counts: dict, compared_with: int | None) -> RunHeader:
    return RunHeader(
        id=run["id"],
        site=run["site_id"],
        status=run["status"],
        window_size=run["window_size"],
        window_start=run["window_start"],
        window_end=run["window_end"],
        created_at=run["started_at"],
        finished_at=run["finished_at"],
        rule_version=run["rule_version"],
        prompt_version=run["prompt_version"],
        model=run["model"],
        compared_with_run_id=compared_with,
        counts={k: counts[k] for k in ("new", "open", "gone", "total")},
        error=run["error"],
    )


async def run_header(conn, site_id: str, run: dict) -> RunHeader:
    counts = (await queries.run_change_counts(conn, [run["id"]]))[run["id"]]
    prev = await queries.previous_run_id(conn, site_id, run["id"])
    return header(run, counts, prev)


@router.get("", response_model=RecommendationList)
async def list_recommendations(
    conn: Conn,
    site: Site,
    run: int | None = None,
    pattern: Annotated[str | None, Query(pattern="^P[1-5]$")] = None,
    confidence: Annotated[str | None, Query(pattern="^(high|medium|low)$")] = None,
    change: Annotated[str | None, Query(pattern="^(new|open|gone)$")] = None,
) -> RecommendationList:
    row = await queries.latest_run(conn, site, run)
    if row is None:
        if run is not None:
            raise not_found("run", run)
        return RecommendationList(run=None, empty_reason="no_run", items=[], gone=[])
    recs = await queries.list_recommendations(conn, row["id"], pattern, confidence, change)
    hdr = await run_header(conn, site, row)
    rows = [item(r) for r in recs]
    reason = "no_candidates" if hdr.counts["total"] == 0 else None
    return RecommendationList(
        run=hdr,
        empty_reason=reason,
        items=[r for r in rows if r.change != "gone"],
        gone=[r for r in rows if r.change == "gone"],
    )


@router.get("/runs", response_model=Paged[RunHeader])
async def list_runs(conn: Conn, site: Site, paging: PagingDep) -> Paged[RunHeader]:
    runs, total = await queries.list_recommendation_runs(conn, site, paging.limit, paging.offset)
    counts = await queries.run_change_counts(conn, [r["id"] for r in runs])
    items = []
    for r in runs:
        prev = await queries.previous_run_id(conn, site, r["id"])
        items.append(header(r, counts[r["id"]], prev))
    return Paged(items=items, page=paging.info(total))


@router.post("/generate", response_model=GenerateResult)
async def generate_now(
    conn: Conn,
    site: Site,
    window: Annotated[str, Query(pattern=WINDOW_PATTERN)] = "6h",
) -> GenerateResult:
    from src.services import pipeline  # lazy: the pipeline module imports many services

    try:
        await pipeline.run_recommendations(site, window)
    except pipeline.LockTaken as exc:
        raise error(
            409, "lock_taken", "A pipeline run is active. Try again in a few minutes."
        ) from exc
    except pipeline.RunFailed as exc:
        log.exception("generate recommendations failed", extra={"run_id": exc.run_id})
        raise error(
            500,
            "run_failed",
            f"Run {exc.run_id} failed at {exc.failed_step}: {exc.error}. "
            "The previous list is still valid.",
        ) from exc
    except Exception as exc:
        log.exception("generate recommendations failed")
        raise error(
            500, "run_failed", f"Run failed: {exc}. The previous list is still valid."
        ) from exc
    row = await queries.latest_run(conn, site)
    return GenerateResult(
        status="completed", run=await run_header(conn, site, row) if row else None
    )


@router.get("/{rec_id}", response_model=RecommendationDetail)
async def get_recommendation(conn: Conn, site: Site, rec_id: int) -> RecommendationDetail:
    r = await queries.get_recommendation(conn, site, rec_id)
    if r is None:
        raise not_found("recommendation", rec_id)
    run = await queries.latest_run(conn, site, r["run_id"])
    evidence = r["evidence"] or {}
    sessions = [str(s) for s in evidence.get("sessions", [])]
    events = [int(e) for e in evidence.get("events", [])]
    llm = r["text_source"] == "llm"
    note = (
        f"Written by LLM ({r['model']}, prompt {r['prompt_version']}), checked against facts"
        if llm
        else "Template text (LLM unavailable or failed check)"
    )
    return RecommendationDetail(
        **item(r).model_dump(),
        reason=LabeledText(text=r["reason"], label="observed"),
        evidence=EvidenceRef(
            sessions_count=r["sessions_count"],
            events_count=r["events_count"],
            session_ids=sessions,
            event_ids=events,
        ),
        potential_issue=LabeledText(text=r["potential_issue"], label="inferred"),
        suggested_validation=LabeledText(text=r["suggested_validation"], label="inferred"),
        next_action=LabeledText(text=r["next_action"], label="unknown"),
        model=r["model"],
        prompt_version=r["prompt_version"],
        text_source_note=note,
        fact_bundle=r["bundle"] or {},
        history=[
            HistoryEntry(
                run_id=h["run_id"],
                recommendation_id=h["id"],
                rank=h["rank"],
                score=h["score"],
                change=h["change"],
            )
            for h in r["history"]
        ],
        first_seen_run_id=r["history"][0]["run_id"],
        related=[brief(x) for x in r["related"]],
        run=await run_header(conn, site, run),
    )
