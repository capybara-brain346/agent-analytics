import json
from datetime import timedelta

import httpx
import pytest
from psycopg.rows import dict_row

from src.config import get_settings
from src.services import recommendations
from src.services.recommendations import scoring
from src.services.recommendations.llm import LLMError, OpenRouterClient, default_client
from src.services.recommendations.text import template_text, validate_llm_text
from tests.factories import NOW, make_agent, make_page_stats, make_session
from tests.recommendations.helpers import FakeLLM, blocked_page


async def rows(conn, run_id=None):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "select * from recommendations where run_id = coalesce(%s, run_id) order by id",
            [run_id],
        )
        return await cur.fetchall()


async def run(conn, **kw):
    return await recommendations.generate(conn, "example", "6h", now=NOW, **kw)


def test_score_example():
    assert recommendations.score(3, 2, 3, 1.0) == 18
    assert scoring.frequency_factor(4) == 1
    assert scoring.frequency_factor(5) == 2
    assert scoring.frequency_factor(50) == 2
    assert scoring.frequency_factor(51) == 3
    assert scoring.confidence_label(1, 1, 1) == "low"
    assert scoring.confidence_label(0, 0, 0) == "low"
    assert scoring.confidence_label(3, 1, 0) == "high"


async def test_p2_pricing_scores_18(conn):
    await blocked_page(conn, "/pricing", sessions=5)
    run_id = await run(conn)
    [rec] = await rows(conn, run_id)
    assert (rec["pattern"], rec["target"], rec["score"]) == ("P2", "/pricing", 18)
    assert (rec["impact"], rec["frequency"], rec["severity"]) == (3, 2, 3)
    assert float(rec["confidence_factor"]) == 1.0 and rec["confidence"] == "high"
    assert set(rec["factor_reasons"]) == {"impact", "frequency", "severity", "confidence"}
    assert rec["rank"] == 1 and rec["change"] == "new" and rec["text_source"] == "template"
    assert rec["recommended_test"] == "Agent fetch of /pricing"
    assert rec["sessions_count"] == 5 and rec["events_count"] == 5
    assert len(rec["evidence"]["sessions"]) == 5 and len(rec["evidence"]["events"]) == 5
    assert "Unknown" in rec["next_action"] and "simulation" in rec["next_action"]
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("select * from recommendation_runs where id = %s", [run_id])
        r = await cur.fetchone()
    assert r["status"] == "success" and r["window_size"] == "6h" and r["rule_version"]
    assert r["counts"]["new"] == 1


async def test_bundle_contents(conn):
    await blocked_page(conn, "/pricing", sessions=5)
    await make_agent(conn, claimed_agent="gptbot", verification="VERIFIED")
    await make_session(  # a related candidate on the same journey
        conn, session_id="r", pages_in_order=["/pricing", "/signup"], key_pages_visited=2
    )
    await make_page_stats(conn, path="/signup", traffic_class=2, n_429=6, requests=6)
    await run(conn)
    bundle = next(
        r for r in await rows(conn) if r["pattern"] == "P2" and r["target"] == "/pricing"
    )["bundle"]
    classes = {c["class"]: c for c in bundle["class_status"]}
    assert classes[2]["n_403"] == 6 and classes[5]["n_2xx"] == 20
    assert (
        bundle["agents"][0]["agent"] == "gptbot"
        and bundle["agents"][0]["verification"] == "VERIFIED"
    )
    assert bundle["time_pattern"]["first_seen"] and bundle["time_pattern"]["peak_hours_utc"]
    assert bundle["access_policy"]["blocked_by_intent"] is False
    assert bundle["journey_position"][0] == {
        "journey_id": "signup", "critical": True, "step_no": 1, "steps_total": 3,
    }  # fmt: skip
    assert {r["target"] for r in bundle["related"]} == {"/signup"}
    assert len(bundle["samples"]) == 5 and bundle["samples"][0]["status"] == 403
    assert {"id", "ts", "path"} <= set(bundle["samples"][0])


def test_validator_catches_invented_facts():
    bundle = {
        "pattern": "P2", "target": "/pricing", "sessions_count": 12, "events_count": 40,
        "class_status": [{"class": 2, "n_403": 6}],
        "agents": [{"agent": "gptbot"}],
    }  # fmt: skip
    ok = {
        "reason": "12 sessions got 403 on /pricing. gptbot was blocked.",
        "potential_issue": "A rule may block /pricing.",
        "suggested_validation": "Request /pricing as gptbot.",
        "next_action": "Unknown: outcome. Simulate.",
    }
    assert validate_llm_text(ok, bundle)
    assert not validate_llm_text(ok | {"reason": "13 sessions got 403."}, bundle)
    assert not validate_llm_text(ok | {"reason": "Blocked on /checkout."}, bundle)
    assert not validate_llm_text(ok | {"reason": "claudebot was blocked."}, bundle)
    assert not validate_llm_text({k: v for k, v in ok.items() if k != "reason"}, bundle)
    assert not validate_llm_text(ok | {"next_action": " "}, bundle)


def test_validator_numbers_must_be_facts_not_timestamps():
    bundle = {
        "pattern": "P2", "target": "/pricing", "sessions_count": 3, "events_count": 40,
        "window": "6h", "agents": [{"agent": "gptbot"}],
        "samples": [{"id": 4217, "ts": "2026-01-01T07:42:10+00:00", "status": 403}],
        "time_pattern": {"first_seen": "2026-01-01T07:42:10+00:00", "peak_hours_utc": [7]},
    }  # fmt: skip
    ok = {
        "reason": "3 sessions got status 403 in 6 hours. Peak hour 7.",
        "potential_issue": "A rule may block /pricing.",
        "suggested_validation": "Request /pricing.",
        "next_action": "Simulate.",
    }
    assert validate_llm_text(ok, bundle)
    assert not validate_llm_text(ok | {"reason": "42 sessions were blocked."}, bundle)
    assert not validate_llm_text(ok | {"reason": "4217 sessions were blocked."}, bundle)
    assert not validate_llm_text(ok | {"reason": "10 sessions were blocked."}, bundle)


async def test_template_passes_validator(conn):
    await blocked_page(conn)
    await make_agent(conn)
    await run(conn)
    bundle = (await rows(conn))[0]["bundle"]
    assert validate_llm_text(template_text("P2", bundle), bundle)


async def test_llm_text_used_and_stored(conn):
    await blocked_page(conn)
    llm = FakeLLM()
    run_id = await run(conn, llm=llm)
    [rec] = await rows(conn, run_id)
    assert rec["text_source"] == "llm" and rec["reason"].startswith("Checked.")
    assert (
        rec["model"] == "fake-model" and rec["prompt_version"] == get_settings().llm_prompt_version
    )


@pytest.mark.parametrize(
    "llm",
    [
        FakeLLM(error=RuntimeError("offline")),
        FakeLLM(text_fn=lambda b: FakeLLM.good(b) | {"reason": "999 sessions on /nowhere"}),
    ],
)
async def test_template_fallback(conn, llm):
    await blocked_page(conn)
    run_id = await run(conn, llm=llm)
    [rec] = await rows(conn, run_id)
    assert rec["text_source"] == "template" and rec["model"] is None
    assert "Unknown" in rec["next_action"]
    async with conn.cursor() as cur:
        await cur.execute("select count(*) from llm_text_cache")
        assert (await cur.fetchone())[0] == 0


async def test_cache_hit(conn):
    await blocked_page(conn)
    llm = FakeLLM()
    await run(conn, llm=llm)
    run2 = await run(conn, llm=llm)
    assert llm.calls == 1
    [rec] = await rows(conn, run2)
    assert rec["text_source"] == "llm"
    # A new prompt version is a cache miss.
    llm2 = FakeLLM()
    llm2.model = "other-model"
    await run(conn, llm=llm2)
    assert llm2.calls == 1


async def test_new_open_gone(conn):
    await blocked_page(conn, "/pricing")
    first = await run(conn)
    await conn.execute("delete from page_stats")
    await conn.execute("delete from sessions")
    await blocked_page(conn, "/products")
    second = await recommendations.generate(conn, "example", "6h", now=NOW + timedelta(minutes=1))
    changes = {r["target"]: r["change"] for r in await rows(conn, second)}
    assert changes == {"/products": "new", "/pricing": "gone"}
    gone = next(r for r in await rows(conn, second) if r["change"] == "gone")
    assert gone["rank"] is None and gone["reason"]
    await blocked_page(conn, "/pricing")
    third = await recommendations.generate(conn, "example", "6h", now=NOW + timedelta(minutes=2))
    changes = {r["target"]: r["change"] for r in await rows(conn, third)}
    assert changes == {"/products": "open", "/pricing": "new"}  # gone item is not "open" again
    assert len(await rows(conn, first)) == 1


async def test_llm_client_http():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = request.headers
        seen["body"] = json.loads(request.content)
        reply = {
            "reason": "r",
            "potential_issue": "p",
            "suggested_validation": "s",
            "next_action": "n",
        }
        return httpx.Response(200, json=chat_result(json.dumps(reply)))

    settings = get_settings().model_copy(
        update={"openrouter_api_key": "k", "llm_base_url": "http://llm/api/v1", "llm_model": "m/x"}
    )
    client = OpenRouterClient(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    out = await client.write_text({"pattern": "P2"})
    assert out["reason"] == "r"
    assert seen["url"] == "http://llm/api/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer k"
    assert seen["body"]["model"] == "m/x"
    assert seen["body"]["response_format"] == {"type": "json_object"}

    for response in (httpx.Response(500), httpx.Response(200, json=chat_result("no json"))):
        transport = httpx.MockTransport(lambda r, response=response: response)
        bad = OpenRouterClient(settings, httpx.AsyncClient(transport=transport))
        with pytest.raises(LLMError):
            await bad.write_text({})


def test_default_client_needs_key_and_model():
    settings = get_settings()
    assert default_client(settings.model_copy(update={"openrouter_api_key": None})) is None
    no_model = settings.model_copy(update={"openrouter_api_key": "k", "llm_model": None})
    assert default_client(no_model) is None
    both = settings.model_copy(update={"openrouter_api_key": "k", "llm_model": "m/x"})
    assert default_client(both).model == "m/x"


def chat_result(content: str) -> dict:
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 1,
        "model": "m/x",
        "system_fingerprint": None,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
    }


async def test_fractional_score_is_stored_exactly(conn):
    await blocked_page(conn, "/pricing", sessions=5)
    await conn.execute("update sessions set confidence = 'medium'")
    run_id = await run(conn)
    [rec] = await rows(conn, run_id)
    assert str(rec["score"]) == "10.8"


async def test_p4_ratio_comes_from_settings(conn, monkeypatch):
    monkeypatch.setenv("P4_BYTES_RATIO", "0.5")
    get_settings.cache_clear()
    await blocked_page(conn, "/pricing", sessions=5)
    run_id = await run(conn)
    [rec] = await rows(conn, run_id)
    assert rec["bundle"]["thresholds"]["p4_bytes_ratio"] == 0.5
