from psycopg.rows import dict_row

from src.services import classify
from tests.factories import CHROME_UA, make_verdict


async def rows(conn):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("select * from verdicts order by id")
        return await cur.fetchall()


async def test_fills_null_rows(conn, clean_db):
    v = await make_verdict(conn)
    spoof = await make_verdict(conn, client_ip="1.2.3.4", verdict="SPOOFED")
    res = await classify.classify_new_verdicts(conn, "example")
    assert res["classified"] == 2
    got = {r["id"]: r for r in await rows(conn)}
    r = got[v["id"]]
    assert r["traffic_class"] == 2 and r["confidence"] == "high"
    assert r["rule_version"] == classify.RULE_VERSION and r["rule_id"]
    assert r["class_evidence"] and r["classified_at"] and r["ua_type"] == "bot"
    s = got[spoof["id"]]
    assert s["traffic_class"] == 6 and "spoofed" in s["flags"]


async def test_never_overwrites(conn, clean_db):
    done = await make_verdict(conn, classified=True, rule_id="OLD", traffic_class=3)
    res = await classify.classify_new_verdicts(conn, "example")
    assert res["classified"] == 0
    (r,) = await rows(conn)
    assert (r["id"], r["rule_id"], r["traffic_class"]) == (done["id"], "OLD", 3)
    again = await classify.classify_new_verdicts(conn, "example")
    assert again["classified"] == 0


async def test_other_site_untouched_and_browser(conn, clean_db):
    other = await make_verdict(conn, site_id="other")
    b = await make_verdict(
        conn,
        user_agent=CHROME_UA,
        claimed_agent=None,
        registry_category=None,
        verdict="UNKNOWN",
        method="none",
        edge_signal="human",
    )
    await classify.classify_new_verdicts(conn, "example")
    got = {r["id"]: r for r in await rows(conn)}
    assert got[other["id"]]["traffic_class"] is None
    assert got[b["id"]]["traffic_class"] == 5
    assert got[b["id"]]["ua_type"] == "browser"
