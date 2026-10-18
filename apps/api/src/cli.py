import asyncio
from collections.abc import Awaitable, Callable
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from src.config import get_settings
from src.logger import configure_logging
from src.models.domain import Lane, SourceType
from src.services import cleanup, importer, pipeline, verify
from src.store import db

app = typer.Typer(no_args_is_help=True)


class WorkerLanes(StrEnum):
    FAST = "fast"
    SLOW = "slow"
    ALL = "all"


@app.callback()
def main() -> None:
    configure_logging(get_settings().log_level)


def run_with_pool[T](job: Callable[[], Awaitable[T]]) -> T:
    async def wrapped() -> T:
        await db.open_pool(get_settings())
        try:
            return await job()
        finally:
            await db.close_pool()

    return asyncio.run(wrapped())


@app.command("worker")
def run_worker(
    lanes: Annotated[
        WorkerLanes, typer.Option(help="fast, slow, or all (two loops in one process)")
    ] = WorkerLanes.ALL,
) -> None:
    asyncio.run(pipeline.run_forever(lanes.value))


@app.command("run-pipeline")
def run_pipeline(
    lane: Lane,
    site: Annotated[str, typer.Option(help="Site ID")],
) -> None:
    result = run_with_pool(lambda: pipeline.run_lane(site, lane))
    if result is None:
        typer.echo(f"Skipped: another run holds the {lane.value} lock for {site}", err=True)
        raise typer.Exit(2)
    typer.echo(f"run {result.run_id}: {result.status}")
    if result.status != "success":
        typer.echo(f"failed at {result.failed_step}: {result.error}", err=True)
        raise typer.Exit(1)


@app.command("run-recommendations")
def run_recommendations(
    site: Annotated[str, typer.Option(help="Site ID")],
    window: Annotated[str | None, typer.Option(help="For example 6h or 14d")] = None,
) -> None:
    window = window or get_settings().recommendation_window
    try:
        run_id = run_with_pool(lambda: pipeline.run_recommendations(site, window))
    except pipeline.LockTaken:
        typer.echo(f"Skipped: recommendations already run for {site}", err=True)
        raise typer.Exit(1) from None
    except pipeline.RunFailed as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    typer.echo(f"recommendation run {run_id}")


@app.command("import")
def import_file(
    path: Path,
    site: Annotated[str, typer.Option(help="Site ID")],
    now: Annotated[bool, typer.Option("--now", help="Import at once, do not wait")] = False,
    force: Annotated[bool, typer.Option("--force", help="Bypass the sha256 check")] = False,
    source: Annotated[SourceType | None, typer.Option(help="Log source: cdn or origin")] = None,
) -> None:
    extra = {"source": source.value} if source else {}
    run_with_pool(lambda: importer.import_local_file(path, site, now=now, force=force, **extra))


@app.command("cleanup")
def run_cleanup() -> None:
    run_with_pool(cleanup.run_cleanup)


@app.command("download-ip-lists")
def download_ip_lists() -> None:
    run_with_pool(verify.download_snapshots)


if __name__ == "__main__":
    app()
