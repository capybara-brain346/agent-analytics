from pathlib import Path

from typer.testing import CliRunner

from src import cli
from src.models.domain import Lane
from src.services import pipeline
from src.store import db

runner = CliRunner()


def patch_pool(monkeypatch):
    events = []

    async def open_pool(settings):
        events.append("open")

    async def close_pool():
        events.append("close")

    monkeypatch.setattr(db, "open_pool", open_pool)
    monkeypatch.setattr(db, "close_pool", close_pool)
    return events


def test_run_pipeline_wired(monkeypatch):
    events = patch_pool(monkeypatch)
    calls = []

    async def run_lane(site, lane):
        calls.append((site, lane))
        return pipeline.RunResult("rid", "success", None, None, {})

    monkeypatch.setattr(cli.pipeline, "run_lane", run_lane)
    result = runner.invoke(cli.app, ["run-pipeline", "fast", "--site", "example"])
    assert result.exit_code == 0, result.output
    assert calls == [("example", Lane.FAST)]
    assert events == ["open", "close"]


def test_run_pipeline_failed_exit_code(monkeypatch):
    patch_pool(monkeypatch)

    async def run_lane(site, lane):
        return pipeline.RunResult("rid", "failed", "verify", "boom", {})

    monkeypatch.setattr(cli.pipeline, "run_lane", run_lane)
    result = runner.invoke(cli.app, ["run-pipeline", "fast", "--site", "example"])
    assert result.exit_code == 1


def test_run_pipeline_skipped_when_locked(monkeypatch):
    patch_pool(monkeypatch)

    async def run_lane(site, lane):
        return None

    monkeypatch.setattr(cli.pipeline, "run_lane", run_lane)
    result = runner.invoke(cli.app, ["run-pipeline", "slow", "--site", "example"])
    assert result.exit_code == 2


def test_run_recommendations_wired_and_lock_error(monkeypatch):
    events = patch_pool(monkeypatch)
    calls = []

    async def run_recommendations(site, window):
        calls.append((site, window))
        return "rec-1"

    monkeypatch.setattr(cli.pipeline, "run_recommendations", run_recommendations)
    result = runner.invoke(cli.app, ["run-recommendations", "--site", "example", "--window", "14d"])
    assert result.exit_code == 0 and "rec-1" in result.output
    assert calls == [("example", "14d")]
    assert events == ["open", "close"]

    async def locked(site, window):
        raise pipeline.LockTaken()

    monkeypatch.setattr(cli.pipeline, "run_recommendations", locked)
    result = runner.invoke(cli.app, ["run-recommendations", "--site", "example"])
    assert result.exit_code == 1


def test_import_wired(monkeypatch, tmp_path: Path):
    events = patch_pool(monkeypatch)
    calls = []

    async def import_local_file(path, site, **kwargs):
        calls.append((path, site, kwargs))

    monkeypatch.setattr(cli.importer, "import_local_file", import_local_file)
    file = tmp_path / "a.log"
    file.write_text("x")
    result = runner.invoke(
        cli.app, ["import", str(file), "--site", "example", "--now", "--force", "--source", "cdn"]
    )
    assert result.exit_code == 0, result.output
    assert calls == [(file, "example", {"now": True, "force": True, "source": "cdn"})]
    assert events == ["open", "close"]
    calls.clear()
    runner.invoke(cli.app, ["import", str(file), "--site", "example"])
    assert calls == [(file, "example", {"now": False, "force": False})]


def test_cleanup_and_download_wired(monkeypatch):
    events = patch_pool(monkeypatch)
    calls = []

    async def cleanup():
        calls.append("cleanup")
        return 3

    async def download():
        calls.append("download")

    monkeypatch.setattr(cli.cleanup, "run_cleanup", cleanup)
    monkeypatch.setattr(cli.verify, "download_snapshots", download)
    assert runner.invoke(cli.app, ["cleanup"]).exit_code == 0
    assert runner.invoke(cli.app, ["download-ip-lists"]).exit_code == 0
    assert calls == ["cleanup", "download"]
    assert events == ["open", "close", "open", "close"]


def test_worker_wired(monkeypatch):
    called = []

    async def run_forever(mode="all"):
        called.append(mode)

    monkeypatch.setattr(cli.pipeline, "run_forever", run_forever)
    assert runner.invoke(cli.app, ["worker"]).exit_code == 0
    assert runner.invoke(cli.app, ["worker", "--lanes", "slow"]).exit_code == 0
    assert called == ["all", "slow"]


def test_import_folder_reads_site_and_source_from_names(monkeypatch, tmp_path: Path):
    patch_pool(monkeypatch)
    calls = []

    async def import_local_file(path, site, **kwargs):
        calls.append((path.name, site, kwargs.get("source")))
        return {"file_id": "f", "duplicate": False}

    monkeypatch.setattr(cli.importer, "import_local_file", import_local_file)
    for name in ("example__origin__20261001T0000Z.log", "example__cdn__20261001T0000Z__a.log.gz"):
        (tmp_path / name).write_text("x")
    (tmp_path / "README.md").write_text("not a log")
    result = runner.invoke(cli.app, ["import", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [
        ("example__cdn__20261001T0000Z__a.log.gz", "example", "cdn"),
        ("example__origin__20261001T0000Z.log", "example", "origin"),
    ]

    (tmp_path / "old.log").write_text("x")
    assert runner.invoke(cli.app, ["import", str(tmp_path)]).exit_code == 2
