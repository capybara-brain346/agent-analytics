"""Command line: worker loop, manual pipeline runs, imports (decisions 1.2, 7.1).

Run: `uv run python -m src.cli --help`
"""

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from src.config import get_settings
from src.logger import configure_logging
from src.models.domain import Lane
from src.services import cleanup, importer, ip_lists, pipeline, worker

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    configure_logging(get_settings().log_level)


@app.command("worker")
def run_worker() -> None:
    """Run the worker loop: take due sites, run their lanes (Flow 7)."""
    asyncio.run(worker.run_forever())


@app.command("run-pipeline")
def run_pipeline(
    lane: Lane,
    site: Annotated[str, typer.Option(help="Site ID")],
) -> None:
    """Run one lane for one site now. fast = steps 1–4, slow = recommendations."""
    asyncio.run(pipeline.run_lane(site, lane))


@app.command("run-recommendations")
def run_recommendations(
    site: Annotated[str, typer.Option(help="Site ID")],
    window: Annotated[str | None, typer.Option(help="For example 6h or 14d")] = None,
) -> None:
    """Generate recommendations now (Flow 5)."""
    asyncio.run(pipeline.run_recommendations(site, window or get_settings().recommendation_window))


@app.command("import")
def import_file(
    path: Path,
    site: Annotated[str, typer.Option(help="Site ID")],
    now: Annotated[bool, typer.Option("--now", help="Import at once, do not wait")] = False,
    force: Annotated[bool, typer.Option("--force", help="Bypass the sha256 check")] = False,
) -> None:
    """Put a log file into the inbox as backfill (decisions 1.1, 1.2, 1.9, 1.18)."""
    asyncio.run(importer.import_local_file(path, site, now=now, force=force))


@app.command("cleanup")
def run_cleanup() -> None:
    """Delete raw files with status success and age > retention (decision 1.10)."""
    asyncio.run(cleanup.delete_expired_raw_files())


@app.command("download-ip-lists")
def download_ip_lists() -> None:
    """Download vendor IP lists as a new snapshot (decision 2.8b)."""
    asyncio.run(ip_lists.download_snapshots())


if __name__ == "__main__":
    app()
