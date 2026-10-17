from datetime import timedelta

from src.services import pairing
from tests.factories import NOW, make_event

WINDOW = 5
WAIT = timedelta(minutes=10)


async def cdn(conn, rid="r1", ts=NOW, **o):
    values = {
        "source": "cdn",
        "pair_state": "pending",
        "edge_request_id": rid,
        "status": 403,
        "edge_status": 403,
        "ts": ts,
    } | o
    return await make_event(conn, **values)


async def origin(conn, rid="r1", ts=NOW, **o):
    values = {
        "source": "origin",
        "pair_state": "pending",
        "edge_request_id": rid,
        "status": 200,
        "origin_status": 200,
        "request_id": "o-1",
        "response_time_ms": 42,
        "ts": ts,
    } | o
    return await make_event(conn, **values)


async def rows(conn):
    cur = await conn.execute("select * from events order by id")
    return [
        dict(zip([c.name for c in cur.description], r, strict=True)) for r in await cur.fetchall()
    ]


async def test_exact_match(conn, config_dir):
    c = await cdn(conn, edge_status=200, status=200)
    await origin(conn, status=500, origin_status=500, ts=NOW + timedelta(seconds=1))
    result = await pairing.pair_events(conn, "example", now=NOW)
    assert result == {"paired": 1, "single": 0, "cdn_bypass": 0}
    [row] = await rows(conn)
    assert row["id"] == c["id"]
    assert (row["source"], row["pair_state"]) == ("paired", "paired")
    assert row["origin_status"] == 500
    assert row["edge_status"] == 200
    assert row["status"] == 200
    assert row["request_id"] == "o-1"
    assert row["response_time_ms"] == 42


async def test_edge_block_status_is_final(conn, config_dir):
    await cdn(conn)
    await origin(conn)
    await pairing.pair_events(conn, "example", now=NOW)
    [row] = await rows(conn)
    assert (row["status"], row["edge_status"], row["origin_status"]) == (403, 403, 200)


async def test_window_edges(conn, config_dir):
    await cdn(conn, "in")
    await origin(conn, "in", ts=NOW - timedelta(seconds=WINDOW))
    await cdn(conn, "out")
    await origin(conn, "out", ts=NOW + timedelta(seconds=WINDOW, milliseconds=1))
    result = await pairing.pair_events(conn, "example", now=NOW)
    assert result["paired"] == 1
    assert len(await rows(conn)) == 3


async def test_nearest_wins_one_to_one(conn, config_dir):
    c1 = await cdn(conn, ts=NOW)
    c2 = await cdn(conn, ts=NOW + timedelta(seconds=4))
    near = await origin(conn, ts=NOW + timedelta(seconds=1), request_id="near")
    far = await origin(conn, ts=NOW + timedelta(seconds=5), request_id="far")
    result = await pairing.pair_events(conn, "example", now=NOW)
    assert result["paired"] == 2
    by_id = {r["id"]: r for r in await rows(conn)}
    assert set(by_id) == {c1["id"], c2["id"]}
    assert by_id[c1["id"]]["request_id"] == "near"
    assert by_id[c2["id"]]["request_id"] == "far"
    assert near["id"] not in by_id and far["id"] not in by_id


async def test_extra_candidate_stays_pending(conn, config_dir):
    await cdn(conn)
    await origin(conn, ts=NOW + timedelta(seconds=1))
    extra = await origin(conn, ts=NOW + timedelta(seconds=2))
    result = await pairing.pair_events(conn, "example", now=NOW)
    assert result == {"paired": 1, "single": 0, "cdn_bypass": 0}
    left = [r for r in await rows(conn) if r["pair_state"] == "pending"]
    assert [r["id"] for r in left] == [extra["id"]]


async def test_wrong_method_or_path_no_pair(conn, config_dir):
    await cdn(conn, "a")
    await origin(conn, "a", method="POST")
    await cdn(conn, "b")
    await origin(conn, "b", path="/other")
    result = await pairing.pair_events(conn, "example", now=NOW)
    assert result["paired"] == 0
    assert len(await rows(conn)) == 4


async def test_wait_expiry(conn, config_dir):
    old = NOW - WAIT - timedelta(seconds=1)
    await cdn(conn, "c", ts=old)
    await origin(conn, "o", ts=old)
    await origin(conn, "x", ts=NOW - WAIT + timedelta(seconds=1))
    result = await pairing.pair_events(conn, "example", now=NOW)
    assert result == {"paired": 0, "single": 2, "cdn_bypass": 1}
    r = await rows(conn)
    assert (r[0]["source"], r[0]["pair_state"], r[0]["cdn_bypass"]) == ("cdn", "single", False)
    assert (r[1]["source"], r[1]["pair_state"], r[1]["cdn_bypass"]) == ("origin", "single", True)
    assert r[2]["pair_state"] == "pending"


async def test_missing_request_id_becomes_single_after_wait(conn, config_dir):
    await cdn(conn, None)
    await origin(conn, None)
    assert (await pairing.pair_events(conn, "example", now=NOW))["paired"] == 0
    result = await pairing.pair_events(conn, "example", now=NOW + WAIT + timedelta(seconds=1))
    assert result["single"] == 2


async def test_late_arrival_both_orders(conn, config_dir):
    await cdn(conn, "a")
    await pairing.pair_events(conn, "example", now=NOW)
    await origin(conn, "a")
    assert (await pairing.pair_events(conn, "example", now=NOW))["paired"] == 1
    await origin(conn, "b")
    await pairing.pair_events(conn, "example", now=NOW)
    await cdn(conn, "b")
    assert (await pairing.pair_events(conn, "example", now=NOW))["paired"] == 1
    assert {r["pair_state"] for r in await rows(conn)} == {"paired"}


async def test_non_pairing_site_noop(conn, config_dir):
    (config_dir / "sites" / "solo.yaml").write_text("site_id: solo\nsources: [origin]\n")
    await make_event(conn, site_id="solo", pair_state="pending", edge_request_id="r1")
    await make_event(conn, site_id="solo", pair_state="pending", edge_request_id="r1", ts=NOW)
    result = await pairing.pair_events(conn, "solo", now=NOW + WAIT * 2)
    assert result == {"paired": 0, "single": 0, "cdn_bypass": 0}
    assert all(r["pair_state"] == "pending" for r in await rows(conn))


async def test_other_site_untouched(conn, config_dir):
    await cdn(conn, site_id="other")
    await origin(conn, site_id="other")
    assert (await pairing.pair_events(conn, "example", now=NOW))["paired"] == 0
    assert len(await rows(conn)) == 2


async def test_rerun_idempotent(conn, config_dir):
    await cdn(conn)
    await origin(conn)
    await cdn(conn, "lonely", ts=NOW - WAIT * 2)
    first = await pairing.pair_events(conn, "example", now=NOW)
    before = await rows(conn)
    second = await pairing.pair_events(conn, "example", now=NOW)
    assert first == {"paired": 1, "single": 1, "cdn_bypass": 0}
    assert second == {"paired": 0, "single": 0, "cdn_bypass": 0}
    assert await rows(conn) == before
