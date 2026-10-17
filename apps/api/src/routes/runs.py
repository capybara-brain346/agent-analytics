from typing import Annotated

from fastapi import APIRouter, Query

from src.models.api import Paged, PipelineRunOut
from src.routes.params import Conn, PagingDep, Site, error, not_found
from src.store import queries

router = APIRouter(prefix="/runs", tags=["runs"])


def run_out(r: dict) -> PipelineRunOut:
    finished = r["finished_at"]
    return PipelineRunOut(
        id=r["id"],
        site=r["site_id"],
        lane=r["lane"],
        status=r["status"],
        started_at=r["started_at"],
        finished_at=finished,
        duration_seconds=(finished - r["started_at"]).total_seconds() if finished else None,
        failed_step=r["failed_step"],
        error=r["error"],
        counts=r["counts"] or {},
    )


@router.get("", response_model=Paged[PipelineRunOut])
async def list_runs(
    conn: Conn,
    site: Site,
    paging: PagingDep,
    lane: Annotated[str | None, Query(pattern="^(fast|slow)$")] = None,
    status: Annotated[str | None, Query(pattern="^(running|success|failed)$")] = None,
) -> Paged[PipelineRunOut]:
    rows, total = await queries.list_pipeline_runs(
        conn, site, lane, status, paging.limit, paging.offset
    )
    return Paged(items=[run_out(r) for r in rows], page=paging.info(total))


@router.get("/{run_id}", response_model=PipelineRunOut)
async def get_run(conn: Conn, site: Site, run_id: str) -> PipelineRunOut:
    import uuid

    try:
        uuid.UUID(run_id)
    except ValueError as exc:
        raise error(422, "bad_run_id", "run id must be a UUID") from exc
    r = await queries.get_pipeline_run(conn, site, run_id)
    if r is None:
        raise not_found("pipeline_run", run_id)
    return run_out(r)
