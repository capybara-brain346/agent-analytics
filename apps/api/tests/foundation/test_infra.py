import gzip

from psycopg import AsyncConnection

from src.models.keys import client_key
from tests import factories
from tests.fakes import MemoryInbox


async def test_schema_has_all_tables(conn: AsyncConnection) -> None:
    cur = await conn.execute("select tablename from pg_tables where schemaname = 'public'")
    names = {row[0] for row in await cur.fetchall()}
    expected = {
        "import_files", "import_rejects", "events", "verdicts", "ip_list_snapshots", "sessions",
        "open_sessions", "session_events", "page_stats", "journey_steps", "agents",
        "recommendation_runs", "recommendations", "llm_text_cache", "pipeline_runs", "site_work",
        "alerts",
    }  # fmt: skip
    assert expected <= names


async def test_events_partition_function_is_idempotent(conn: AsyncConnection) -> None:
    cur = await conn.execute("select ensure_events_partition('2026-01-05')")
    assert (await cur.fetchone())[0] == "events_20260105"
    await conn.execute("select ensure_events_partition('2026-01-05')")
    cur = await conn.execute("select count(*) from pg_tables where tablename = 'events_20260105'")
    assert (await cur.fetchone())[0] == 1


async def test_event_dedupe_index(conn: AsyncConnection) -> None:
    import psycopg
    import pytest

    await factories.make_event(conn, line_key="same")
    with pytest.raises(psycopg.errors.UniqueViolation):
        await factories.make_event(conn, line_key="same")


async def test_make_event_defaults(conn: AsyncConnection) -> None:
    event = await factories.make_event(conn)
    assert event["path"] == "/pricing"
    assert event["status"] == 200
    assert event["client_key"] == client_key(factories.GPTBOT_UA, factories.GPTBOT_IP)
    assert str(event["client_ip"]) == factories.GPTBOT_IP


async def test_each_test_starts_empty(conn: AsyncConnection) -> None:
    cur = await conn.execute("select count(*) from events")
    assert (await cur.fetchone())[0] == 0


async def test_all_factories_insert(conn: AsyncConnection) -> None:
    f = factories
    file = await f.make_import_file(conn)
    await f.make_event(conn, file_id=file["id"])
    await f.make_verdict(conn, classified=True)
    await f.make_session(conn)
    await f.make_session(conn, open=True)
    await f.make_session_event(conn)
    await f.make_page_stats(conn)
    await f.make_journey_step(conn)
    await f.make_agent(conn)
    rec = await f.make_recommendation(conn)
    assert rec["run_id"]
    await f.make_pipeline_run(conn)
    await f.make_site_work(conn)
    await f.make_alert(conn)
    snap = await f.make_ip_list_snapshot(conn)
    assert snap["prefixes"]


async def test_conn_commits_at_once(conn: AsyncConnection, db_url: str) -> None:
    await factories.make_event(conn)
    async with await AsyncConnection.connect(db_url) as other:
        cur = await other.execute("select count(*) from events")
        assert (await cur.fetchone())[0] == 1


async def test_pool_fixture(pool) -> None:
    async with pool.connection() as c:
        cur = await c.execute("select 1")
        assert (await cur.fetchone())[0] == 1


async def test_client_fixture(client) -> None:
    assert (await client.get("/livez")).json() == {"status": "ok"}


async def test_memory_inbox_gzip_and_plain() -> None:
    inbox = MemoryInbox()
    inbox.put_text("a", "l1\nl2\r\nl3")
    inbox.put_text("b", "x\ny", gzipped=True)
    assert [line async for line in inbox.open_lines("a")] == ["l1", "l2", "l3"]
    assert [line async for line in inbox.open_lines("b")] == ["x", "y"]


async def test_memory_inbox_put_stream_and_delete() -> None:
    inbox = MemoryInbox()

    async def chunks():
        yield b"ab"
        yield b"c"

    sha, size = await inbox.put_stream("k", chunks())
    import hashlib

    assert (sha, size) == (hashlib.sha256(b"abc").hexdigest(), 3)
    await inbox.delete("k")
    await inbox.delete("k")
    assert "k" not in inbox.objects
    assert gzip.decompress(gzip.compress(b"x")) == b"x"
