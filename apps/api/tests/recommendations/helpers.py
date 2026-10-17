from uuid import uuid4

from src.services.recommendations import template_text
from tests.factories import (
    make_event,
    make_page_stats,
    make_session,
    make_session_event,
)


class FakeLLM:
    model = "fake-model"

    def __init__(self, text_fn=None, error: Exception | None = None):
        self.calls = 0
        self.error = error
        self.text_fn = text_fn or self.good

    @staticmethod
    def good(bundle: dict) -> dict:
        text = template_text(bundle["pattern"], bundle)
        return text | {"reason": "Checked. " + text["reason"]}

    async def write_text(self, bundle: dict) -> dict:
        self.calls += 1
        if self.error:
            raise self.error
        return self.text_fn(bundle)


async def blocked_page(conn, path="/pricing", sessions=5, **stats):
    await make_page_stats(conn, path=path, traffic_class=2, n_2xx=0, n_403=6, requests=6, **stats)
    await make_page_stats(
        conn, path=path, traffic_class=5, n_2xx=20, requests=20, median_bytes=5000, tags=[]
    )
    ids = []
    for i in range(sessions):
        s = await make_session(
            conn,
            session_id=f"{path}-s{i}-{uuid4().hex[:6]}",
            pages_in_order=[path],
            key_pages_visited=1,
            status_counts={"403": 1},
        )
        e = await make_event(conn, path=path, status=403, line_key=f"{path}-{i}-{uuid4().hex}")
        await make_session_event(
            conn, session_id=s["session_id"], event_id=e["id"], event_ts=e["ts"], seq=i
        )
        ids.append(s["session_id"])
    return ids
