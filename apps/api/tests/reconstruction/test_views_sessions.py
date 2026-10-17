from datetime import timedelta

from psycopg import AsyncConnection

from src.store import views
from tests.factories import NOW
from tests.reconstruction.test_views import all_sessions, rows, run, seed

AGENT = {"registry_category": "agent_client"}


async def test_split_never_gives_two_sessions_the_same_id(conn: AsyncConnection) -> None:
    base = NOW - timedelta(hours=1)
    await seed(conn, [(0, "/a", 200), (10, "/b", 200), (20, "/c", 200)], base=base)
    other = await seed(conn, [(0, "/o", 200)], base=base, ip="20.171.7.7")
    await run(conn, now=NOW)
    (other_before,) = [s for s in await all_sessions(conn) if str(s["client_ip"]) == "20.171.7.7"]
    await seed(conn, [(-5, "/late", 200)], base=base)  # id kept, started moves back
    await run(conn, now=NOW + timedelta(minutes=1))
    (first,) = [s for s in await all_sessions(conn) if str(s["client_ip"]) != "20.171.7.7"]
    # a newer verdict makes the gap 2 min for the whole range: the session splits
    await seed(conn, [(25, "/d", 200)], base=base, verdict=AGENT)
    await run(conn, now=NOW + timedelta(minutes=2))
    sessions = [s for s in await all_sessions(conn) if str(s["client_ip"]) != "20.171.7.7"]
    ids = [s["session_id"] for s in sessions]
    assert len(sessions) == 5 and len(set(ids)) == 5
    assert sessions[0]["session_id"] == first["session_id"]  # oldest part keeps the id
    (other_after,) = [s for s in await all_sessions(conn) if str(s["client_ip"]) == "20.171.7.7"]
    assert other_after["session_id"] == other_before["session_id"]
    (n,) = await rows(conn, "select count(distinct session_id) as n from session_events")
    assert n["n"] == 6  # 5 + the other client
    assert other


async def test_session_length_is_capped(conn: AsyncConnection) -> None:
    base = NOW - timedelta(days=3)
    await seed(conn, [(m, "/pricing", 200) for m in range(0, 3 * 24 * 60, 10)], base=base)
    await run(conn, now=NOW)
    sessions = await all_sessions(conn)
    assert len(sessions) >= 3
    cap = timedelta(hours=views.MAX_SESSION_HOURS)
    assert all(s["last_seen"] - s["started"] <= cap for s in sessions)
    assert sum(s["requests"] for s in sessions) == 3 * 24 * 6
    # a re-run builds the same ids and splits
    before = [(s["session_id"], s["requests"]) for s in sessions]
    await seed(conn, [(3 * 24 * 60 + 1, "/pricing", 200)], base=base)
    await run(conn, now=NOW + timedelta(minutes=2))
    after = [(s["session_id"], s["requests"]) for s in await all_sessions(conn)]
    assert after[: len(before) - 1] == before[:-1]


async def test_continuous_client_refreshes_bounded_hours(conn: AsyncConnection) -> None:
    base = NOW - timedelta(days=3)
    await seed(conn, [(m, "/pricing", 200) for m in range(0, 3 * 24 * 60, 10)], base=base)
    first = await run(conn, now=NOW)
    assert first["hours_updated"] >= 72
    await seed(conn, [(3 * 24 * 60 + 1, "/pricing", 200)], base=base)
    second = await run(conn, now=NOW + timedelta(minutes=2))
    assert second["hours_updated"] <= 2
    third = await run(conn, now=NOW + timedelta(minutes=3))
    assert third["hours_updated"] == 0


async def test_session_split_refreshes_hours_of_parts_without_new_event(
    conn: AsyncConnection,
) -> None:
    base = (NOW - timedelta(hours=3)).replace(minute=0)
    await seed(
        conn, [(10, "/p", 200), (25, "/p", 200), (50, "/p", 200), (65, "/p", 200)], base=base
    )
    await run(conn, now=NOW)
    q = "select sum(sessions) as n from {t} where hour = %s"
    assert (await rows(conn, q.format(t="page_stats"), base))[0]["n"] == 1
    assert (await rows(conn, q.format(t="agents"), base))[0]["n"] == 1
    # new event in hour 1; the agent verdict splits the session into 4 parts
    await seed(conn, [(70, "/p", 200)], base=base, verdict=AGENT)
    r = await run(conn, now=NOW + timedelta(minutes=1))
    assert (await rows(conn, q.format(t="page_stats"), base))[0]["n"] == 3
    assert (await rows(conn, q.format(t="agents"), base))[0]["n"] == 3
    hour1 = base + timedelta(hours=1)
    assert (await rows(conn, q.format(t="page_stats"), hour1))[0]["n"] == 2
    assert r["hours_updated"] == 2  # hour 0 (changed ids) + hour 1 (new event)


async def test_unchanged_hours_of_a_grown_session_are_not_refreshed(
    conn: AsyncConnection,
) -> None:
    base = (NOW - timedelta(hours=5)).replace(minute=0)
    await seed(conn, [(m, "/p", 200) for m in range(0, 240, 20)], base=base)
    await run(conn, now=NOW)
    await seed(conn, [(241, "/q", 200)], base=base)
    r = await run(conn, now=NOW + timedelta(minutes=1))
    assert r["hours_updated"] == 1
