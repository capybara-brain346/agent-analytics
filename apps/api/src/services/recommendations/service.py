import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

from psycopg import AsyncConnection

from src.config import get_settings
from src.models.domain import RegistryCategory
from src.services.recommendations import scoring, text
from src.services.recommendations.llm import default_client
from src.services.registry import load_registry
from src.services.site_config import SiteConfig, load_site_config
from src.store import recommendations as store

RULE_VERSION = "2"
_WINDOW = re.compile(r"^(\d+)([mhd])$")
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_window(window: str) -> timedelta:
    match = _WINDOW.match(window.strip())
    if not match or int(match.group(1)) == 0:
        raise ValueError(f"Invalid window: {window!r} (use 6h, 14d, 30m)")
    return timedelta(**{_UNITS[match.group(2)]: int(match.group(1))})


def stable_id(pattern: str, target: str, journey_id: str | None) -> str:
    raw = f"{pattern}|{target}|{journey_id or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def bundle_hash(bundle: dict) -> str:
    raw = json.dumps(bundle, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def task_agents() -> list[str]:
    return [e.id for e in load_registry()[1] if e.category == RegistryCategory.AGENT_CLIENT]


def _candidate(pattern: str, target: str, row: dict, **extra) -> dict:
    return {
        "pattern": pattern,
        "target": target,
        "journey_id": None,
        "kind": None,
        "step_no": None,
        "paths": [target],
        "is_key": False,
        "session_ids": list(row.get("session_ids") or []),
        "sessions_count": row.get("sessions_count") or 0,
        "n_high": row.get("n_high") or 0,
        "n_medium": row.get("n_medium") or 0,
        "n_low": row.get("n_low") or 0,
    } | extra


async def find_candidates(conn: AsyncConnection, cfg: SiteConfig, start: datetime) -> list[dict]:
    settings = get_settings()
    site = cfg.site_id
    key_set = set(cfg.key_pages) | set(cfg.conversion_pages)
    agents = task_agents()
    found = []

    row = await store.p1_product_discovery(conn, site, start, settings.p1_min_key_pages, agents)
    if row:
        target = cfg.conversion_pages[0] if cfg.conversion_pages else "conversion"
        found.append(_candidate("P1", target, row, paths=list(cfg.key_pages), is_key=True))

    for row in await store.p2_blocked_access(
        conn, site, start, sorted(key_set), settings.p2_min_blocks
    ):
        if cfg.access_policy.blocked_by_intent(row["path"]):
            continue
        found.append(_candidate("P2", row["path"], row, is_key=True, blocks=row["blocks"]))

    for row in await store.p3_broken_navigation(
        conn, site, start, settings.p3_min_sessions, agents
    ):
        found.append(
            _candidate(
                "P3",
                row["step_path"],
                row,
                journey_id=row["journey_id"],
                step_no=row["step_no"],
                is_key=row["step_path"] in key_set,
            )
        )

    if cfg.site_pages:
        for row in await store.p4_content_discovery(
            conn, site, start, cfg.site_pages, settings.p4_bytes_ratio
        ):
            found.append(
                _candidate("P4", row["path"], row, kind=row["kind"], is_key=row["path"] in key_set)
            )

    journeys = [j for j in cfg.journeys if j.critical and len(j.steps) >= 2]
    specs = [
        {"id": j.id, "first_path": j.steps[0], "final_no": len(j.steps), "final_path": j.steps[-1]}
        for j in journeys
    ]
    by_id = {j.id: j for j in journeys}
    for row in await store.p5_full_journey(conn, site, start, specs, agents):
        journey = by_id[row["journey_id"]]
        found.append(
            _candidate(
                "P5",
                journey.steps[-1],
                row,
                journey_id=journey.id,
                paths=list(journey.steps),
                is_key=True,
            )
        )
    return found


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _journey_ids(cfg: SiteConfig, cand: dict) -> list[str]:
    if cand["journey_id"]:
        return [cand["journey_id"]]
    if cand["pattern"] == "P1":
        return []
    return [j.id for j in cfg.journeys if cand["target"] in j.steps]


def _journey_position(cfg: SiteConfig, cand: dict, ids: list[str]) -> list[dict]:
    out = []
    for journey in cfg.journeys:
        if journey.id not in ids:
            continue
        step_no = (
            journey.steps.index(cand["target"]) + 1 if cand["target"] in journey.steps else None
        )
        if cand["pattern"] == "P3":
            step_no = cand["step_no"]
        out.append(
            {
                "journey_id": journey.id,
                "critical": journey.critical,
                "step_no": step_no,
                "steps_total": len(journey.steps),
            }
        )
    return out


async def build_bundle(
    conn: AsyncConnection, cfg: SiteConfig, start: datetime, cand: dict, window: str
) -> dict:
    settings = get_settings()
    site = cfg.site_id
    ids = cand["session_ids"]
    paths = cand["paths"]
    journey_ids = _journey_ids(cfg, cand)

    status = []
    for row in await store.class_status(conn, site, start, paths):
        row["class"] = row.pop("traffic_class")
        row["class_name"] = text.class_name(row["class"])
        status.append(row)

    agents = []
    for row in await store.agents_for_sessions(conn, site, start, ids, paths):
        agents.append(
            {
                "agent": row["agent"],
                "class": row["traffic_class"],
                "verification": row["verification"],
                "sessions": row["sessions"],
            }
        )

    time_pattern = {
        k: _iso(v) for k, v in (await store.time_pattern(conn, site, start, ids, paths)).items()
    }
    samples = [
        {k: _iso(v) for k, v in row.items()}
        for row in await store.sample_events(conn, site, ids, paths, 5)
    ]
    funnel = (
        await store.journey_funnel(conn, site, start, journey_ids, task_agents())
        if journey_ids
        else []
    )
    policy = cfg.access_policy
    return {
        "pattern": cand["pattern"],
        "target": cand["target"],
        "journey_id": cand["journey_id"],
        "kind": cand["kind"],
        "step_no": cand["step_no"],
        "paths": paths,
        "window": window,
        "sessions_count": cand["sessions_count"],
        "events_count": cand["events_count"],
        "class_status": status,
        "agents": agents,
        "time_pattern": time_pattern,
        "access_policy": {
            "path": cand["target"],
            "blocked_by_intent": policy.blocked_by_intent(cand["target"]),
            "allow": policy.allow,
            "block": policy.block,
            "robots_disallow": policy.robots_disallow,
        },
        "journey_position": _journey_position(cfg, cand, journey_ids),
        "journey_funnel": funnel,
        "related": [],
        "samples": samples,
        "thresholds": {
            "p1_min_key_pages": settings.p1_min_key_pages,
            "p2_min_blocks": settings.p2_min_blocks,
            "p3_min_sessions": settings.p3_min_sessions,
            "p4_bytes_ratio": settings.p4_bytes_ratio,
            "frequency_mid_min": settings.frequency_mid_min,
            "frequency_high_over": settings.frequency_high_over,
        },
    }


async def _write_text(
    conn: AsyncConnection, site_id: str, bundle: dict, llm, stats: dict
) -> tuple[dict, str]:
    template = text.template_text(bundle["pattern"], bundle)
    if llm is None:
        stats["template"] += 1
        return template, "template"
    prompt_version = get_settings().llm_prompt_version
    digest = bundle_hash(bundle)
    cached = await store.cached_text(conn, site_id, digest, llm.model, prompt_version)
    if cached:
        stats["cache_hits"] += 1
        stats["llm"] += 1
        return cached, "llm"
    try:
        written = await llm.write_text(bundle)
    except Exception:
        written = None
    if written is None or not text.validate_llm_text(written, bundle):
        stats["template"] += 1
        return template, "template"
    await store.save_cached_text(conn, site_id, digest, written, llm.model, prompt_version)
    stats["llm"] += 1
    return written, "llm"


async def generate(
    conn: AsyncConnection,
    site_id: str,
    window: str,
    now: datetime | None = None,
    llm=None,
) -> int:
    settings = get_settings()
    delta = parse_window(window)
    now = now or datetime.now(UTC)
    start = now - delta
    cfg = load_site_config(site_id)
    if llm is None:
        llm = default_client(settings)
    prompt_version = settings.llm_prompt_version
    model = getattr(llm, "model", None) if llm else None

    run_id = await store.create_run(
        conn, site_id, window, start, now, RULE_VERSION, prompt_version, model
    )

    candidates = await find_candidates(conn, cfg, start)
    for cand in candidates:
        cand["events_count"] = await store.count_events(conn, site_id, cand["session_ids"])
        cand["scored"] = scoring.factors(
            cand["pattern"],
            cand["kind"],
            cand["target"],
            cand["is_key"],
            cand["sessions_count"],
            cand["n_high"],
            cand["n_medium"],
            cand["n_low"],
        )
    candidates.sort(
        key=lambda c: (-c["scored"]["score"], -c["sessions_count"], c["pattern"], c["target"])
    )

    journeys_of = {id(c): set(_journey_ids(cfg, c)) for c in candidates}
    stats = {"llm": 0, "template": 0, "cache_hits": 0}
    items = []
    for rank, cand in enumerate(candidates, start=1):
        bundle = await build_bundle(conn, cfg, start, cand, window)
        bundle["related"] = [
            {
                "pattern": other["pattern"],
                "target": other["target"],
                "score": round(other["scored"]["score"], 1),
            }
            for other in candidates
            if other is not cand and journeys_of[id(cand)] & journeys_of[id(other)]
        ]
        fields, source = await _write_text(conn, site_id, bundle, llm, stats)
        scored = cand["scored"]
        items.append(
            {
                "run_id": run_id,
                "site_id": site_id,
                "stable_id": stable_id(cand["pattern"], cand["target"], cand["journey_id"]),
                "rank": rank,
                "pattern": cand["pattern"],
                "target": cand["target"],
                "journey_id": cand["journey_id"],
                "score": round(scored["score"], 1),
                "impact": scored["impact"],
                "frequency": scored["frequency"],
                "severity": scored["severity"],
                "confidence_factor": scored["confidence_factor"],
                "confidence": scored["confidence"],
                "factor_reasons": scored["factor_reasons"],
                "recommended_test": text.recommended_test(cand["pattern"], bundle),
                "reason": fields["reason"],
                "evidence": {
                    "sessions": cand["session_ids"],
                    "events": await store.event_ids(conn, site_id, cand["session_ids"]),
                },
                "sessions_count": cand["sessions_count"],
                "events_count": cand["events_count"],
                "potential_issue": fields["potential_issue"],
                "suggested_validation": fields["suggested_validation"],
                "next_action": fields["next_action"],
                "text_source": source,
                "model": model if source == "llm" else None,
                "prompt_version": prompt_version if source == "llm" else None,
                "bundle": bundle,
            }
        )

    previous = {p["stable_id"]: p for p in await store.previous_items(conn, site_id, run_id)}
    current = {i["stable_id"] for i in items}
    for item in items:
        item["change"] = "open" if item["stable_id"] in previous else "new"
    gone = []
    for stable, old in previous.items():
        if stable not in current:
            gone.append(
                {k: v for k, v in old.items() if k != "id"}
                | {"run_id": run_id, "rank": None, "change": "gone"}
            )
    await store.insert_recommendations(conn, items + gone)

    by_pattern: dict[str, int] = {}
    for item in items:
        by_pattern[item["pattern"]] = by_pattern.get(item["pattern"], 0) + 1
    counts = {
        "candidates": len(items),
        "new": sum(1 for i in items if i["change"] == "new"),
        "open": sum(1 for i in items if i["change"] == "open"),
        "gone": len(gone),
        "by_pattern": by_pattern,
        "text_llm": stats["llm"],
        "text_template": stats["template"],
        "cache_hits": stats["cache_hits"],
    }
    await store.finish_run(conn, run_id, counts, now)
    return run_id
