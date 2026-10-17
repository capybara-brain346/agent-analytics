from dataclasses import replace
from datetime import timedelta

import pytest

from src.services.recommendations.service import find_candidates, parse_window
from src.services.site_config import load_site_config
from tests.factories import (
    NOW,
    make_journey_step,
    make_page_stats,
    make_session,
)


async def found(conn, pattern):
    cfg = replace(load_site_config("example"), site_pages=["/pricing", "/products", "/docs/api"])
    return [
        c
        for c in await find_candidates(conn, cfg, NOW - timedelta(hours=6))
        if c["pattern"] == pattern
    ]


def test_parse_window():
    assert parse_window("6h") == timedelta(hours=6)
    assert parse_window("14d") == timedelta(days=14)
    with pytest.raises(ValueError):
        parse_window("abc")
    with pytest.raises(ValueError):
        parse_window("0h")


async def test_p1_positive(conn):
    await make_session(conn, session_id="a")
    await make_session(conn, session_id="b", traffic_class=4, open=True)
    [c] = await found(conn, "P1")
    assert c["sessions_count"] == 2 and set(c["session_ids"]) == {"a", "b"}
    assert c["target"] == "/signup"


async def test_p1_negative(conn):
    await make_session(conn, session_id="conv", reached_conversion=True)
    await make_session(conn, session_id="few", key_pages_visited=2)
    await make_session(conn, session_id="browser", traffic_class=5)
    await make_session(conn, session_id="old", last_seen=NOW - timedelta(hours=7))
    assert await found(conn, "P1") == []


async def test_p2_positive(conn):
    await make_page_stats(conn, path="/pricing", traffic_class=2, n_403=3, n_429=2)
    await make_session(conn, session_id="a", pages_in_order=["/pricing"], status_counts={"403": 3})
    [c] = await found(conn, "P2")
    assert c["target"] == "/pricing" and c["sessions_count"] == 1 and c["blocks"] == 5


async def test_p2_negative(conn):
    await make_page_stats(conn, path="/pricing", traffic_class=2, n_403=4)  # below 5
    await make_page_stats(conn, path="/pricing", traffic_class=5, n_403=50)  # browser
    await make_page_stats(conn, path="/other", traffic_class=2, n_403=9)  # not a key page
    await make_page_stats(conn, path="/private/plans", traffic_class=2, n_403=9)  # by intent
    assert await found(conn, "P2") == []


async def test_p3(conn):
    await make_journey_step(conn, step_no=2, step_path="/signup")
    await make_journey_step(conn, step_no=1, step_path="/pricing")
    for i in range(3):
        await make_session(
            conn,
            session_id=f"a{i}",
            pages_in_order=["/pricing", "/signup"],
            has_retry=True,
            retry_paths=["/signup"],
            journeys_reached={"signup": 2},
        )
    for i in range(2):  # below the threshold at /pricing
        await make_session(
            conn,
            session_id=f"b{i}",
            pages_in_order=["/pricing"],
            has_loop=True,
            retry_paths=["/pricing"],
            journeys_reached={"signup": 1},
        )
    [c] = await found(conn, "P3")
    assert (c["target"], c["journey_id"], c["step_no"], c["is_key"]) == (
        "/signup",
        "signup",
        2,
        True,
    )
    assert c["sessions_count"] == 3 and set(c["session_ids"]) == {"a0", "a1", "a2"}


async def test_p3_counts_distinct_sessions_not_hourly_rows(conn):
    # One session over 3 hours with a retry in each hour: 3 hourly rows, 1 session.
    for h in range(3):
        await make_journey_step(
            conn,
            hour=NOW.replace(minute=0) - timedelta(hours=h),
            step_no=2,
            step_path="/signup",
            sessions_retry_or_loop=1,
        )
    await make_session(
        conn,
        session_id="long",
        started=NOW - timedelta(hours=3),
        pages_in_order=["/pricing", "/signup"],
        has_retry=True,
        retry_paths=["/signup"],
        journeys_reached={"signup": 2},
    )
    assert await found(conn, "P3") == []


async def test_p3_retry_elsewhere_does_not_count(conn):
    await make_journey_step(conn, step_no=2, step_path="/signup")
    for i in range(3):  # retry on /docs, only a visit on /signup
        await make_session(
            conn,
            session_id=f"a{i}",
            pages_in_order=["/signup", "/docs"],
            has_retry=True,
            retry_paths=["/docs"],
            journeys_reached={"signup": 2},
        )
    assert await found(conn, "P3") == []


async def test_p3_negative_class(conn):
    await make_journey_step(conn, step_no=2, step_path="/signup", traffic_class=5)
    for i in range(4):
        await make_session(
            conn,
            session_id=f"a{i}",
            traffic_class=5,
            retry_paths=["/signup"],
            pages_in_order=["/signup"],
            journeys_reached={"signup": 2},
        )
    assert await found(conn, "P3") == []


async def test_p4_three_kinds(conn):
    # AI traffic exists, so "never fetched" is meaningful.
    await make_page_stats(conn, path="/pricing", traffic_class=2, n_2xx=0, n_403=3, requests=3)
    await make_page_stats(
        conn, path="/docs/api", traffic_class=2, n_2xx=4, requests=4, median_bytes=100
    )
    await make_page_stats(
        conn, path="/docs/api", traffic_class=5, n_2xx=9, requests=9, median_bytes=9000
    )
    kinds = {c["target"]: c["kind"] for c in await found(conn, "P4")}
    assert kinds == {
        "/pricing": "blocked_or_redirected",
        "/docs/api": "small_response",
        "/products": "never_fetched",
    }


async def test_p4_negative(conn):
    # Normal bytes: no finding. No AI traffic at all: no finding.
    assert await found(conn, "P4") == []
    for path in ("/pricing", "/products", "/docs/api"):
        await make_page_stats(
            conn, path=path, traffic_class=2, requests=4, n_2xx=4, median_bytes=4000
        )
        await make_page_stats(
            conn, path=path, traffic_class=5, requests=9, n_2xx=9, median_bytes=5000
        )
    assert await found(conn, "P4") == []


async def test_p5_positive(conn):
    await make_journey_step(conn, step_no=1, step_path="/pricing")
    await make_journey_step(conn, step_no=3, step_path="/signup/confirm")
    await make_session(
        conn, session_id="a", pages_in_order=["/pricing", "/signup"],
        journeys_reached={"signup": 2},
    )  # fmt: skip
    await make_session(
        conn, session_id="b", pages_in_order=["/pricing"], journeys_reached={"signup": 1}
    )
    [c] = await found(conn, "P5")
    assert c["journey_id"] == "signup" and set(c["session_ids"]) == {"a", "b"}


async def test_p5_negative(conn):
    # One session reached the last step: no finding.
    await make_journey_step(conn, step_no=1, step_path="/pricing")
    await make_session(conn, session_id="a", journeys_reached={"signup": 1})
    await make_session(
        conn,
        session_id="b",
        pages_in_order=["/pricing", "/signup", "/signup/confirm"],
        journeys_reached={"signup": 3},
    )
    # non-critical journey is ignored
    await make_journey_step(conn, journey_id="docs", step_no=1, step_path="/docs")
    await make_session(conn, session_id="c", journeys_reached={"docs": 1})
    assert await found(conn, "P5") == []
