from datetime import timedelta

from src.services.pipeline import retention
from tests.factories import make_import_file, make_pipeline_run

DAYS = 30


async def count(conn, table: str) -> int:
    return (await (await conn.execute(f"select count(*) from {table}")).fetchone())[0]


async def test_prune_derived_removes_old_rows_only(conn, now):
    old, new = now - timedelta(days=DAYS + 1), now - timedelta(days=1)
    for t in (old, new):
        await make_pipeline_run(conn, started_at=t, finished_at=t)
        await conn.execute(
            "insert into page_stats (site_id, hour, path, traffic_class) values ('s', %s, '/', 1)",
            [t],
        )
        await conn.execute(
            "insert into agents (site_id, hour, claimed_agent, traffic_class) "
            "values ('s', %s, 'a', 1)",
            [t],
        )
        await conn.execute(
            "insert into journey_steps (site_id, hour, journey_id, traffic_class, step_no, "
            "step_path) values ('s', %s, 'j', 1, 1, '/')",
            [t],
        )
        await conn.execute(
            "insert into sessions (site_id, session_id, client_key, started, last_seen) "
            "values ('s', %s, 'c', %s, %s)",
            [f"id-{t:%m%d}", t, t],
        )
        await conn.execute(
            "insert into session_events (site_id, session_id, event_id, event_ts, seq) "
            "values ('s', %s, 1, %s, 1)",
            [f"id-{t:%m%d}", t],
        )
        f = await make_import_file(conn, received_at=t, status="success")
        await conn.execute(
            "insert into import_rejects (file_id, site_id, line_no, reason) "
            "values (%s, 's', 1, 'bad')",
            [f["id"]],
        )
    running = await make_pipeline_run(conn, started_at=old, finished_at=None, status="running")

    counts = await retention.prune_derived(conn, DAYS, now=now)

    for table in (
        "page_stats",
        "agents",
        "journey_steps",
        "sessions",
        "session_events",
        "import_rejects",
    ):
        assert await count(conn, table) == 1, table
        assert counts[table] == 1
    assert await count(conn, "pipeline_runs") == 2  # new run + the old one still running
    cur = await conn.execute("select id from pipeline_runs where status = 'running'")
    assert (await cur.fetchone())[0] == running["id"]
