from datetime import UTC, datetime, timedelta

from src.store import events
from tests.factories import NOW


def row(n: int, ts: datetime = NOW, key: str | None = None, ip: str = "20.171.1.5") -> tuple:
    return (
        "example", ts, None, n, "origin", "GET", None, "/p", 200, None, 200, 10, None, None, ip,
        "UA", "ck", None, None, "none", key or f"k{n}", "single", False,
    )  # fmt: skip


async def test_copy_events_inserts_and_skips_duplicates(conn):
    rows = [row(1), row(2), row(2), row(3, ts=NOW - timedelta(days=2))]
    assert await events.copy_events(conn, rows) == 3
    assert await events.copy_events(conn, [row(1), row(4)]) == 1
    assert await events.count_events(conn, "example") == 4


async def test_copy_events_creates_partitions_for_each_utc_day(conn):
    late = datetime(2026, 10, 17, 23, 59, tzinfo=UTC)
    early = datetime(2026, 10, 18, 0, 1, tzinfo=UTC)
    assert await events.copy_events(conn, [row(1, late), row(2, early)]) == 2
    cur = await conn.execute(
        "select to_regclass('events_20261017') is not null,"
        " to_regclass('events_20261018') is not null"
    )
    assert await cur.fetchone() == (True, True)


async def test_copy_events_empty(conn):
    assert await events.copy_events(conn, []) == 0


async def test_copy_events_many_rows(conn):
    rows = [row(i, key=f"k{i}", ip=f"10.0.{i // 250}.{i % 250 + 1}") for i in range(20000)]
    assert await events.copy_events(conn, rows) == 20000


async def test_delete_file_events(conn):
    from tests.factories import make_import_file

    f = await make_import_file(conn)
    r = list(row(1))
    r[2] = f["id"]
    await events.copy_events(conn, [tuple(r), row(2)])
    assert await events.delete_file_events(conn, "example", f["id"]) == 1
    assert await events.count_events(conn, "example") == 1
