from psycopg import AsyncConnection

from src.models.domain import Lane, RunStatus


async def start_run(conn: AsyncConnection, site_id: str, lane: Lane) -> str:
    raise NotImplementedError


async def finish_run(
    conn: AsyncConnection,
    run_id: str,
    status: RunStatus,
    failed_step: str | None = None,
    error: str | None = None,
) -> None:
    raise NotImplementedError


async def last_success_by_lane(conn: AsyncConnection) -> list[dict]:
    raise NotImplementedError
