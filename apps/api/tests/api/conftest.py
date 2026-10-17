from datetime import timedelta

import pytest

from tests.factories import CHROME_UA, GPTBOT_IP, GPTBOT_UA, NOW, make_event, make_verdict

RANGE = {
    "from": (NOW - timedelta(hours=6)).isoformat(),
    "to": (NOW + timedelta(hours=1)).isoformat(),
}


@pytest.fixture
def rng() -> dict:
    return dict(RANGE)


@pytest.fixture
def traffic(conn):
    async def build() -> dict:
        gpt = await make_verdict(conn, classified=True)
        browser = await make_verdict(
            conn,
            classified=True,
            user_agent=CHROME_UA,
            client_ip="198.51.100.7",
            claimed_agent=None,
            registry_category=None,
            verdict="UNKNOWN",
            method="none",
            traffic_class=5,
            confidence="medium",
            ua_type="browser",
        )
        events = [
            await make_event(conn, ts=NOW, path="/pricing", status=200, verdict_id=gpt["id"]),
            await make_event(
                conn,
                ts=NOW - timedelta(minutes=2),
                path="/pricing",
                status=403,
                verdict_id=gpt["id"],
                user_agent=GPTBOT_UA,
                client_ip=GPTBOT_IP,
            ),
            await make_event(
                conn,
                ts=NOW - timedelta(minutes=3),
                path="/docs/api",
                status=200,
                source="cdn",
                verdict_id=gpt["id"],
            ),
            await make_event(
                conn,
                ts=NOW - timedelta(minutes=4),
                path="/pricing",
                status=200,
                user_agent=CHROME_UA,
                client_ip="198.51.100.7",
                verdict_id=browser["id"],
            ),
            await make_event(
                conn, ts=NOW - timedelta(minutes=5), path="/x", status=500, verdict_id=None
            ),
            await make_event(
                conn,
                ts=NOW - timedelta(minutes=1),
                path="/pending",
                pair_state="pending",
                verdict_id=gpt["id"],
            ),
        ]
        return {"gpt": gpt, "browser": browser, "events": events}

    return build
