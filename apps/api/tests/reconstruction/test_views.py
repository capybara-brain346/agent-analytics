from datetime import timedelta

import pytest
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from src.models.keys import client_key
from src.services import reconstruction
from src.store import views
from tests.factories import (
    CHROME_UA,
    GPTBOT_IP,
    GPTBOT_UA,
    NOW,
    make_event,
    make_verdict,
)

T0 = NOW - timedelta(hours=2)  # 10:00


async def rows(conn: AsyncConnection, sql: str, *args) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, list(args))
        return await cur.fetchall()


async def seed(
    conn: AsyncConnection,
    steps: list[tuple[float, str, int]],
    *,
    site: str = "example",
    ua: str = GPTBOT_UA,
    ip: str = GPTBOT_IP,
    verdict: dict | None = None,
    base=T0,
    **event,
) -> list[dict]:
    v = await make_verdict(
        conn, site_id=site, user_agent=ua, client_ip=ip, classified=True, **(verdict or {})
    )
    out = []
    for minutes, path, status in steps:
        out.append(
            await make_event(
                conn,
                site_id=site,
                ts=base + timedelta(minutes=minutes),
                path=path,
                status=status,
                user_agent=ua,
                client_ip=ip,
                verdict_id=v["id"],
                **event,
            )
        )
    return out


async def run(conn: AsyncConnection, site: str = "example", now=NOW) -> dict:
    return await reconstruction.update_views(conn, site, now=now)


async def all_sessions(conn: AsyncConnection, site: str = "example") -> list[dict]:
    return await rows(
        conn,
        """
        select *, 'closed' as state from sessions where site_id = %s
        union all select *, 'open' as state from open_sessions where site_id = %s
        order by started
        """,
        site,
        site,
    )


async def test_split_at_thirty_minutes(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/a", 200), (10, "/b", 200), (41, "/c", 200), (42, "/d", 200)])
    await run(conn)
    s = await all_sessions(conn)
    assert [x["requests"] for x in s] == [2, 2]
    assert s[0]["pages_in_order"] == ["/a", "/b"]
    assert s[0]["state"] == "closed"
    assert s[1]["started"] == T0 + timedelta(minutes=41)


async def test_exactly_thirty_minutes_is_one_session(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/a", 200), (30, "/b", 200)])
    await run(conn)
    assert [x["requests"] for x in await all_sessions(conn)] == [2]


async def test_agent_client_gap_is_two_minutes(conn: AsyncConnection) -> None:
    await seed(
        conn,
        [(0, "/a", 200), (1, "/b", 200), (4, "/c", 200)],
        verdict={"registry_category": "agent_client", "claimed_agent": "chatgpt-user"},
    )
    await run(conn)
    assert [x["requests"] for x in await all_sessions(conn)] == [2, 1]


async def test_retry_flag(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/signup", 403), (0.5, "/signup", 403), (5, "/signup", 200)])
    await run(conn)
    (s,) = await all_sessions(conn)
    assert s["has_retry"] and s["retries"] == 1
    assert s["status_counts"] == {"403": 2, "200": 1}


async def test_no_retry_after_success_or_late(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/a", 200), (0.2, "/a", 200), (5, "/b", 500), (7, "/b", 200)])
    await run(conn)
    (s,) = await all_sessions(conn)
    assert not s["has_retry"] and s["retries"] == 0


async def test_loop_by_repeat_and_by_redirect(conn: AsyncConnection) -> None:
    await seed(conn, [(i, "/x", 200) for i in range(5)])
    await seed(conn, [(0, "/a", 200), (1, "/b", 301), (2, "/a", 200)], ip="20.171.9.9")
    await seed(conn, [(0, "/a", 200), (1, "/b", 200), (2, "/c", 200)], ip="20.171.7.7")
    await run(conn)
    by_ip = {str(s["client_ip"]): s for s in await all_sessions(conn)}
    assert by_ip["20.171.1.5"]["has_loop"]
    assert by_ip["20.171.9.9"]["has_loop"]
    assert not by_ip["20.171.7.7"]["has_loop"]


async def test_key_pages_and_conversion(conn: AsyncConnection) -> None:
    await seed(
        conn,
        [(0, "/pricing", 200), (1, "/pricing", 200), (2, "/blog", 200), (3, "/signup?x=1", 200)],
    )
    await seed(conn, [(0, "/pricing", 200), (1, "/signup", 403)], ip="20.171.2.2")
    await run(conn)
    a, b = sorted(await all_sessions(conn), key=lambda s: -s["requests"])
    assert a["key_pages_visited"] == 1 and a["reached_conversion"]
    assert a["distinct_pages"] == 3
    assert a["pages_in_order"] == ["/pricing", "/blog", "/signup?x=1"]
    assert not b["reached_conversion"]


async def test_journeys_reached(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/pricing", 200), (1, "/signup", 200), (2, "/docs", 200)])
    await run(conn)
    (s,) = await all_sessions(conn)
    assert s["journeys_reached"] == {"signup": 2, "docs": 1}


async def test_session_fields_from_latest_verdict(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/a", 200)])
    v = await make_verdict(
        conn, classified=True, traffic_class=3, claimed_agent="gptbot-fake", verdict="CLAIMED"
    )
    await make_event(conn, ts=T0 + timedelta(minutes=1), verdict_id=v["id"], path="/b")
    await run(conn)
    (s,) = await all_sessions(conn)
    assert s["verdict_id"] == v["id"] and s["traffic_class"] == 3
    assert s["claimed_agent"] == "gptbot-fake"
    assert s["client_key"] == client_key(GPTBOT_UA, GPTBOT_IP)


async def test_not_grouped_and_pending_and_unverified_ignored(conn: AsyncConnection) -> None:
    await make_event(conn, ts=T0, client_key=None, user_agent=None, client_ip=None)
    v = await make_verdict(conn, classified=True)
    await make_event(conn, ts=T0, pair_state="pending", verdict_id=v["id"])
    await make_event(conn, ts=T0, verdict_id=None)
    counts = await run(conn)
    assert await all_sessions(conn) == []
    assert counts["sessions_written"] == 0


async def test_confidence_rules(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/a", 200)], ip="20.171.1.1")  # VERIFIED, not shared
    await seed(conn, [(0, "/a", 200)], ip="100.64.1.1")  # VERIFIED, shared (CGN)
    await seed(
        conn,
        [(0, "/a", 200)],
        ip="20.171.3.3",
        verdict={"registry_category": "agent_client", "claimed_agent": "chatgpt-user"},
    )
    await seed(
        conn,
        [(0, "/a", 200)],
        ip="20.171.4.4",
        verdict={"verdict": "CLAIMED", "traffic_class": 3, "claimed_agent": "x"},
    )
    await seed(
        conn,
        [(0, "/a", 200)],
        ua=CHROME_UA,
        ip="20.171.5.5",
        verdict={
            "verdict": "UNKNOWN",
            "traffic_class": 5,
            "claimed_agent": None,
            "registry_category": None,
        },
    )
    await seed(
        conn,
        [(0, "/a", 200)],
        ip="20.171.6.6",
        verdict={"verdict": "UNKNOWN", "traffic_class": 6, "claimed_agent": None},
    )
    await run(conn)
    by_ip = {str(s["client_ip"]): s for s in await all_sessions(conn)}
    assert by_ip["20.171.1.1"]["confidence"] == "high"
    assert by_ip["100.64.1.1"]["confidence"] == "low" and by_ip["100.64.1.1"]["shared_ip"]
    assert any("shared IP" in g for g in by_ip["100.64.1.1"]["gaps"])
    assert by_ip["20.171.3.3"]["confidence"] == "low"
    assert by_ip["20.171.4.4"]["confidence"] == "medium"
    assert by_ip["20.171.5.5"]["confidence"] == "medium"
    assert by_ip["20.171.6.6"]["confidence"] == "low"


async def test_gaps(conn: AsyncConnection, config_dir) -> None:
    await seed(conn, [(0, "/a", 200)])
    await run(conn)
    (s,) = await all_sessions(conn)
    assert "outcome unknown" in s["gaps"]
    assert not any("no CDN log" in g for g in s["gaps"])
    (config_dir / "sites" / "origin-only.yaml").write_text(
        "site_id: origin-only\nsources: [origin]\n"
    )
    await seed(conn, [(0, "/a", 200)], site="origin-only")
    await run(conn, "origin-only")
    (s,) = await all_sessions(conn, "origin-only")
    assert "no CDN log: edge blocks unknown" in s["gaps"]


async def test_open_then_closed(conn: AsyncConnection) -> None:
    last = NOW - timedelta(minutes=5)
    await seed(conn, [(0, "/a", 200)], base=last - timedelta(minutes=1))
    await seed(conn, [(0, "/a", 200)], base=last, ip="20.171.8.8")
    c = await run(conn)
    assert len(await rows(conn, "select 1 from open_sessions")) == 2
    assert c["sessions_open"] == 2
    # 30 min gap + 10 min margin later: both idle
    c = await run(conn, now=NOW + timedelta(minutes=36))
    assert len(await rows(conn, "select 1 from open_sessions")) == 0
    assert len(await rows(conn, "select 1 from sessions")) == 2
    assert c["sessions_closed"] == 2
    # session_events survive the move
    assert len(await rows(conn, "select 1 from session_events")) == 2


async def test_open_session_grows_and_version_bumps(conn: AsyncConnection) -> None:
    base = NOW - timedelta(minutes=8)
    await seed(conn, [(0, "/pricing", 200), (1, "/docs", 200)], base=base)
    await run(conn)
    (s1,) = await all_sessions(conn)
    v = await make_verdict(conn, classified=True)
    await make_event(
        conn, ts=base + timedelta(minutes=3), path="/signup", status=403, verdict_id=v["id"]
    )
    await run(conn)
    (s2,) = await all_sessions(conn)
    assert s2["session_id"] == s1["session_id"]
    assert s2["version"] == s1["version"] + 1
    assert s2["requests"] == 3 and s2["state"] == "open"
    seqs = await rows(conn, "select seq from session_events order by seq")
    assert [r["seq"] for r in seqs] == [1, 2, 3]


async def test_agent_client_closes_after_gap_plus_margin(conn: AsyncConnection) -> None:
    await seed(
        conn,
        [(0, "/a", 200)],
        base=NOW - timedelta(minutes=11),
        verdict={"registry_category": "agent_client", "claimed_agent": "chatgpt-user"},
    )
    await run(conn)
    assert len(await rows(conn, "select 1 from open_sessions")) == 1  # 11 < 2 + 10
    await run(conn, now=NOW + timedelta(minutes=2))
    assert len(await rows(conn, "select 1 from sessions")) == 1


async def test_idempotent(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/pricing", 200), (1, "/signup", 403), (2, "/signup", 403)])
    await seed(conn, [(100, "/pricing", 200)])
    await run(conn)
    tables = [
        "sessions",
        "open_sessions",
        "session_events",
        "page_stats",
        "agents",
        "journey_steps",
    ]
    before = {t: await rows(conn, f"select * from {t} order by 1, 2, 3") for t in tables}
    c = await run(conn)
    after = {t: await rows(conn, f"select * from {t} order by 1, 2, 3") for t in tables}
    assert before == after
    assert c["clients_recomputed"] == 0


async def test_late_event_recomputes_closed_range(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/a", 200), (50, "/c", 200)])
    await run(conn)
    assert [s["requests"] for s in await all_sessions(conn)] == [1, 1]
    v = await make_verdict(conn, classified=True)
    await make_event(conn, ts=T0 + timedelta(minutes=25), path="/b", verdict_id=v["id"])
    c = await run(conn)
    s = await all_sessions(conn)
    assert [x["requests"] for x in s] == [3]  # the late event bridges the gap: two closed merge
    assert s[0]["pages_in_order"] == ["/a", "/b", "/c"]
    assert c["sessions_recomputed_closed"] >= 1
    assert len(await rows(conn, "select 1 from session_events")) == 3
    stats = await rows(conn, "select sum(requests) n from page_stats")
    assert stats[0]["n"] == 3


async def test_late_event_before_session_start(conn: AsyncConnection) -> None:
    await seed(conn, [(10, "/b", 200)])
    await run(conn)
    old = (await all_sessions(conn))[0]
    v = await make_verdict(conn, classified=True)
    await make_event(conn, ts=T0, path="/a", verdict_id=v["id"])
    await run(conn)
    (s,) = await all_sessions(conn)
    assert s["requests"] == 2 and s["session_id"] == old["session_id"]
    assert len(await rows(conn, "select 1 from session_events")) == 2
    assert len(await rows(conn, "select distinct session_id from session_events")) == 1


async def test_hourly_views(conn: AsyncConnection) -> None:
    base = NOW.replace(minute=0) - timedelta(hours=1)  # 11:00
    await seed(
        conn,
        [
            (5, "/pricing", 200),
            (6, "/signup", 403),
            (6.5, "/signup", 403),
            (7, "/signup", 429),
            (8, "/x", 301),
            (9, "/y", 404),
            (10, "/z", 502),
        ],
        base=base,
        bytes_sent=100,
    )
    await seed(conn, [(5, "/pricing", 200)], base=base, ip="20.171.2.2", bytes_sent=300)
    await seed(
        conn,
        [(20, "/pricing", 200)],
        base=base,
        ua=CHROME_UA,
        ip="20.171.3.3",
        verdict={
            "verdict": "UNKNOWN",
            "traffic_class": 5,
            "claimed_agent": None,
            "ua_type": "browser",
        },
    )
    await seed(conn, [(70, "/pricing", 200)], base=base)  # next hour (12:10)
    await run(conn)
    pricing = await rows(
        conn,
        "select * from page_stats where path = '/pricing' and traffic_class = 2 and hour = %s",
        base,
    )
    (p,) = pricing
    assert p["requests"] == 2 and p["clients"] == 2 and p["sessions"] == 2
    assert p["median_bytes"] == 200 and p["tags"] == ["key"] and p["n_2xx"] == 2
    (s,) = await rows(conn, "select * from page_stats where path = '/signup' and hour = %s", base)
    assert s["tags"] == ["conversion"] and s["requests"] == 3
    assert (s["n_403"], s["n_429"], s["n_4xx"], s["retries"]) == (2, 1, 3, 2)
    assert (await rows(conn, "select n_3xx from page_stats where path='/x'"))[0]["n_3xx"] == 1
    assert (await rows(conn, "select n_5xx from page_stats where path='/z'"))[0]["n_5xx"] == 1
    # two hours exist for /pricing class 2
    assert (
        len(await rows(conn, "select 1 from page_stats where path='/pricing' and traffic_class=2"))
        == 2
    )

    agents = {
        (a["claimed_agent"], a["traffic_class"]): a
        for a in await rows(conn, "select * from agents where hour = %s", base)
    }
    g = agents[("gptbot", 2)]
    assert g["requests"] == 8 and g["sessions"] == 2 and g["distinct_pages"] == 5
    assert g["verification"] == "VERIFIED" and g["top_paths"][0] == "/signup"
    assert g["first_seen"] == base + timedelta(minutes=5)
    assert ("unknown:browser", 5) in agents


async def test_journey_steps(conn: AsyncConnection) -> None:
    base = NOW.replace(minute=0) - timedelta(minutes=30)  # 11:30
    await seed(conn, [(0, "/pricing", 200), (1, "/signup", 403), (1.2, "/signup", 403)], base=base)
    await seed(conn, [(0, "/pricing", 200)], base=base, ip="20.171.2.2")
    await seed(
        conn,
        [(0, "/pricing", 200), (1, "/signup", 200), (2, "/signup/confirm", 200)],
        base=base,
        ip="20.171.3.3",
    )
    await run(conn)
    steps = {
        r["step_no"]: r
        for r in await rows(
            conn, "select * from journey_steps where journey_id = 'signup' and traffic_class = 2"
        )
    }
    assert steps[1]["sessions_reached"] == 3 and steps[1]["step_path"] == "/pricing"
    assert steps[2]["sessions_reached"] == 2 and steps[2]["sessions_retry_or_loop"] == 1
    assert steps[3]["sessions_reached"] == 1 and steps[3]["sessions_retry_or_loop"] == 0


async def test_hourly_not_incremented_on_growth(conn: AsyncConnection) -> None:
    base = NOW - timedelta(minutes=10)
    await seed(conn, [(0, "/pricing", 200)], base=base)
    await run(conn)
    v = await make_verdict(conn, classified=True)
    await make_event(conn, ts=base + timedelta(minutes=1), path="/pricing", verdict_id=v["id"])
    await run(conn)
    (p,) = await rows(conn, "select * from page_stats")
    assert p["requests"] == 2 and p["sessions"] == 1


async def test_multi_site_isolation(conn: AsyncConnection, config_dir) -> None:
    (config_dir / "sites" / "other.yaml").write_text("site_id: other\nsources: [origin]\n")
    await seed(conn, [(0, "/a", 200)])
    await seed(conn, [(0, "/a", 200)], site="other")
    await run(conn, "example")
    assert len(await all_sessions(conn, "other")) == 0
    assert (await rows(conn, "select 1 from page_stats where site_id='other'")) == []
    await run(conn, "other")
    assert len(await all_sessions(conn, "other")) == 1
    assert len(await all_sessions(conn, "example")) == 1
    assert {r["site_id"] for r in await rows(conn, "select site_id from session_events")} == {
        "example",
        "other",
    }


async def test_transaction_rolls_back_on_error(conn: AsyncConnection, monkeypatch) -> None:
    from src.store import views

    await seed(conn, [(0, "/a", 200)])

    async def boom(*a, **k):
        raise RuntimeError("x")

    monkeypatch.setattr(views, "refresh_hours", boom)
    with pytest.raises(RuntimeError):
        await run(conn)
    assert await rows(conn, "select 1 from sessions union all select 1 from open_sessions") == []


async def test_new_work_comes_from_in_views_flag(conn: AsyncConnection) -> None:
    done = await seed(conn, [(0, "/a", 200), (1, "/b", 200)])
    v = await make_verdict(conn, classified=True)
    pending = await make_event(conn, ts=T0, pair_state="pending", verdict_id=v["id"])
    no_verdict = await make_event(conn, ts=T0, verdict_id=None)
    await run(conn)
    flags = {r["id"]: r["in_views"] for r in await rows(conn, "select id, in_views from events")}
    assert all(flags[e["id"]] for e in done)
    assert not flags[pending["id"]] and not flags[no_verdict["id"]]
    # The flag, not session_events, decides: with no session rows the run still finds no work.
    await conn.execute("delete from session_events")
    assert (await run(conn))["clients_recomputed"] == 0


async def test_late_event_is_new_work_again(conn: AsyncConnection) -> None:
    await seed(conn, [(0, "/a", 200)])
    await run(conn)
    await seed(conn, [(5, "/b", 200)])
    assert (await run(conn))["clients_recomputed"] == 1


async def test_not_grouped_events_count_as_unknown_class(conn: AsyncConnection) -> None:
    await make_event(conn, ts=T0, path="/pricing", status=403, client_key=None, user_agent=None)
    await make_event(conn, ts=T0, path="/pricing", status=200, client_key=None, user_agent=None)
    await run(conn)
    assert await all_sessions(conn) == []
    (p,) = await rows(conn, "select * from page_stats where path = '/pricing'")
    assert (p["traffic_class"], p["requests"], p["n_403"], p["n_2xx"]) == (6, 2, 1, 1)
    assert p["sessions"] == 0
    (a,) = await rows(conn, "select * from agents")
    assert (a["traffic_class"], a["requests"], a["claimed_agent"]) == (6, 2, "unknown:ungrouped")
    assert all(r["in_views"] for r in await rows(conn, "select in_views from events"))
    # Done once: a second run changes nothing and finds no work.
    before = await rows(conn, "select * from page_stats")
    await run(conn)
    assert await rows(conn, "select * from page_stats") == before


async def late_event(conn: AsyncConnection, seeded: list[dict], minutes: float, path: str, **kw):
    return await make_event(
        conn,
        ts=T0 + timedelta(minutes=minutes),
        path=path,
        status=kw.pop("status", 200),
        verdict_id=seeded[0]["verdict_id"],
        **kw,
    )


async def test_session_id_stable_when_earlier_event_arrives(conn: AsyncConnection) -> None:
    evs = await seed(conn, [(10, "/pricing", 200), (12, "/docs", 200)])
    await run(conn)
    (first,) = await all_sessions(conn)
    await late_event(conn, evs, 9, "/a")  # one minute before the first event
    await run(conn, now=NOW + timedelta(minutes=1))
    (second,) = await all_sessions(conn)
    assert second["session_id"] == first["session_id"]
    assert second["requests"] == 3 and second["version"] == first["version"] + 1
    (n,) = await rows(conn, "select count(*) as n from session_events")
    assert n["n"] == 3


async def test_merged_sessions_keep_earliest_id_and_drop_the_other(conn: AsyncConnection) -> None:
    evs = await seed(conn, [(0, "/a", 200), (1, "/b", 200), (36, "/c", 200), (37, "/d", 200)])
    await run(conn)
    a, b = await all_sessions(conn)
    await late_event(conn, evs, 20, "/m")
    await run(conn, now=NOW + timedelta(minutes=1))
    (merged,) = await all_sessions(conn)
    assert merged["session_id"] == a["session_id"] and merged["requests"] == 5
    assert (await rows(conn, "select distinct session_id from session_events"))[0][
        "session_id"
    ] == a["session_id"]


async def test_merge_refreshes_hours_of_flags_that_changed(conn: AsyncConnection) -> None:
    # 2 + 2 + 1 late = 5 events on /signup = loop. The loop flag reaches the hour-11 event.
    evs = await seed(conn, [(0, "/signup", 200), (1, "/signup", 200)])
    await seed(conn, [(35, "/signup", 200), (65, "/signup", 200)])
    await run(conn)
    q = "select sessions_retry_or_loop as n from journey_steps where step_no = 2 and hour = %s"
    hour11 = T0 + timedelta(hours=1)
    assert [r["n"] for r in await rows(conn, q, hour11)] == [0]
    await late_event(conn, evs, 20, "/signup")
    await run(conn, now=NOW + timedelta(minutes=1))
    assert [r["n"] for r in await rows(conn, q, hour11)] == [1]


async def test_growth_refreshes_earlier_hours_of_the_session(conn: AsyncConnection) -> None:
    evs = await seed(conn, [(40, "/signup", 200), (45, "/signup", 200), (50, "/signup", 200)])
    await late_event(conn, evs, 55, "/signup")
    await run(conn)
    q = "select sessions_retry_or_loop as n from journey_steps where step_no = 2 and hour = %s"
    assert [r["n"] for r in await rows(conn, q, T0)] == [0]
    await late_event(conn, evs, 65, "/signup")  # 5th request, next hour
    await run(conn, now=NOW + timedelta(minutes=1))
    assert [r["n"] for r in await rows(conn, q, T0)] == [1]


async def test_refresh_hours_scans_only_dirty_hours(conn: AsyncConnection, monkeypatch) -> None:
    old = NOW - timedelta(days=20)
    await seed(conn, [(0, "/a", 200)] * 1, base=old, ip="20.171.4.4")
    await seed(conn, [(0, "/a", 200)] * 1, base=T0, ip="20.171.5.5")
    # 20 other events in the 20 days between, already in views
    for d in range(1, 20):
        await seed(conn, [(0, "/b", 200)], base=NOW - timedelta(days=d), ip="20.171.6.6")
    scanned = {}
    sql_of = {}
    real = views._temp

    async def spy(c, name, select, params):
        n = await real(c, name, select, params)
        scanned[name] = n
        sql_of[name] = select
        return n

    monkeypatch.setattr(views, "_temp", spy)
    await run(conn)
    assert scanned["_he"] == 21  # all dirty here
    scanned.clear()
    await seed(conn, [(0, "/z", 200)], base=old + timedelta(days=1, hours=1), ip="20.171.4.4")
    await seed(conn, [(5, "/z", 200)], base=T0 + timedelta(hours=1), ip="20.171.5.5")
    await run(conn, now=NOW + timedelta(minutes=1))
    assert scanned["_he"] <= 4  # two dirty hours, not 20 days
    # The event range must come from each dirty hour, not from min(hour)..max(hour).
    assert "min(hour)" not in sql_of["_he"] and "max(hour)" not in sql_of["_he"]


async def test_retry_paths_stored_once_per_session(conn: AsyncConnection) -> None:
    steps = []
    for h in range(3):  # a retry on /signup in each of 3 hours: one session
        steps += [(h * 60, "/pricing", 200), (h * 60 + 10, "/signup?x=1", 404)]
        steps += [(h * 60 + 10.5, "/signup?x=1", 404), (h * 60 + 30, "/pricing", 200)]
    await seed(conn, steps)
    await run(conn)
    (s,) = await all_sessions(conn)
    assert s["has_retry"] and {"/signup?x=1", "/signup"} <= set(s["retry_paths"])
