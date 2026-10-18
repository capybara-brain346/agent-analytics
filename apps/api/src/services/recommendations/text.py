import json
import re

from src.models.domain import Pattern
from src.services import registry

TEXT_FIELDS = ("reason", "potential_issue", "suggested_validation", "next_action")

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_PATH = re.compile(r"(?<![\w/:.])/[\w][\w./\-~%]*|(?<![\w/:.])/(?![\w/])")
_PUNCT = ".,;:)"
_CLASS_NAMES = {
    1: "verified search crawler",
    2: "known AI crawler",
    3: "other identifiable bot",
    4: "browser automation",
    5: "ordinary browser",
    6: "unknown",
}


def class_name(traffic_class: int) -> str:
    return _CLASS_NAMES.get(traffic_class, "unknown")


def _clean_path(path: str) -> str:
    return path.rstrip(_PUNCT) or path


def _paths(text: str) -> set[str]:
    return {_clean_path(p) for p in _PATH.findall(text)}


def _agents(bundle: dict) -> str:
    names = [a["agent"] for a in bundle.get("agents", []) if a.get("agent")]
    return ", ".join(names) if names else "no named agent"


def _status_line(bundle: dict) -> str:
    parts = []
    for row in bundle.get("class_status", []):
        parts.append(
            f"{row['class_name']}: {row['requests']} requests, {row['n_2xx']} with status 2xx, "
            f"{row['n_3xx']} with status 3xx, {row['n_403']} with status 403, "
            f"{row['n_429']} with status 429"
        )
    return "; ".join(parts) if parts else "no page statistics in this window"


def _sessions(bundle: dict) -> str:
    return f"{bundle['sessions_count']} sessions and {bundle['events_count']} events"


def recommended_test(pattern: Pattern | str, bundle: dict) -> str:
    pattern = str(pattern)
    target = bundle["target"]
    if pattern == "P1":
        paths = " → ".join(bundle.get("paths", [])) or "key pages"
        return f"Agent journey {paths} → {target}"
    if pattern == "P2":
        return f"Agent fetch of {target}"
    if pattern == "P3":
        return (
            f"Agent journey {bundle.get('journey_id')} at step {bundle.get('step_no')} ({target})"
        )
    if pattern == "P4":
        return f"Agent discovery of {target} from the site start page"
    paths = " → ".join(bundle.get("paths", []))
    return f"Agent journey {bundle.get('journey_id')}: {paths}"


def template_text(pattern: Pattern | str, bundle: dict) -> dict:
    pattern = str(pattern)
    target = bundle["target"]
    agents = _agents(bundle)
    sessions = _sessions(bundle)
    unknown = (
        "Unknown: the outcome and the intent of the agent. Logs show requests and "
        "status codes only. A simulation with a real agent is needed to see the outcome."
    )
    if pattern == "P1":
        k = bundle["thresholds"]["p1_min_key_pages"]
        return {
            "reason": (
                f"{bundle['sessions_count']} agent sessions visited at least {k} key pages "
                f"and did not reach a conversion page. Agents: {agents}. Evidence: {sessions}."
            ),
            "potential_issue": (
                f"Agents may not find the step from the product pages to {target}, "
                "or may not be able to use it."
            ),
            "suggested_validation": (
                f"Run an agent over the key pages and try to reach {target}. "
                "Check status codes and links at each step."
            ),
            "next_action": f"Simulate the agent journey. {unknown}",
        }
    if pattern == "P2":
        return {
            "reason": (
                f"Agents get blocked on {target}. {_status_line(bundle)}. "
                f"Agents: {agents}. Evidence: {sessions}. The access policy allows this page."
            ),
            "potential_issue": (
                f"A rule at the edge or the origin may block agents from {target} "
                "by mistake. The rule may be a bot rule, a rate limit, or a login wall."
            ),
            "suggested_validation": (
                f"Request {target} as the listed agents and as a browser. "
                "Compare the status codes. Find the rule that returns 403 or 429."
            ),
            "next_action": f"Simulate an agent fetch of {target}. {unknown}",
        }
    if pattern == "P3":
        return {
            "reason": (
                f"{bundle['sessions_count']} agent sessions retried or looped at step "
                f"{bundle.get('step_no')} of journey {bundle.get('journey_id')} ({target}). "
                f"Agents: {agents}. Evidence: {sessions}."
            ),
            "potential_issue": (
                f"The page {target} may return an error, a redirect loop, or a link "
                "that agents cannot follow."
            ),
            "suggested_validation": (
                f"Follow journey {bundle.get('journey_id')} to step {bundle.get('step_no')} "
                "with an agent. Check each redirect and each status code."
            ),
            "next_action": f"Simulate this journey step. {unknown}",
        }
    if pattern == "P4":
        return {
            "reason": _p4_reason(bundle, target, agents, sessions),
            "potential_issue": (
                f"Agents may not discover {target}, or may get a response that has little "
                "content for them."
            ),
            "suggested_validation": (
                f"Check that {target} is linked, is in the sitemap, and returns the same "
                "content to agents and to browsers."
            ),
            "next_action": f"Simulate discovery of {target}. {unknown}",
        }
    return {
        "reason": (
            f"Agents started journey {bundle.get('journey_id')} but no agent reached the last "
            f"step ({target}). Agents: {agents}. Evidence: {sessions}."
        ),
        "potential_issue": (
            f"Agents may stop before the last step of journey {bundle.get('journey_id')}. "
            "A step may need a login, a form, or a script that agents cannot use."
        ),
        "suggested_validation": (
            f"Run an agent through journey {bundle.get('journey_id')} from the first step to "
            "the last. Record where it stops."
        ),
        "next_action": f"Simulate the full journey. {unknown}",
    }


def _p4_reason(bundle: dict, target: str, agents: str, sessions: str) -> str:
    kind = bundle.get("kind")
    if kind == "never_fetched":
        return f"No AI crawler fetched {target} in this window. {_status_line(bundle)}."
    if kind == "blocked_or_redirected":
        return (
            f"AI crawlers fetched {target} but got status 403 or 3xx and no status 2xx. "
            f"{_status_line(bundle)}. Agents: {agents}. Evidence: {sessions}."
        )
    return (
        f"AI crawlers got status 200 on {target} with far fewer bytes than browsers. "
        f"{_status_line(bundle)}. Agents: {agents}. Evidence: {sessions}."
    )


# Numbers the text may use without a bundle fact: the HTTP status words of the prompt and the
# templates ("status 403", "status 429", "2xx", "3xx"). All other numbers must be bundle facts.
_FIXED_NUMBERS = {2.0, 3.0, 403.0, 429.0}
# Bundle keys that hold identifiers or time stamps, not facts. Their digits do not count.
_NON_FACT_KEYS = {"id", "ts", "class", "first_seen", "last_seen", "session_ids", "event_ids"}


def _fact_numbers(value, key: str | None = None) -> set[float]:
    if key in _NON_FACT_KEYS:
        return set()
    if isinstance(value, bool):
        return set()
    if isinstance(value, (int, float)):
        return {float(value)}
    if isinstance(value, dict):
        out: set[float] = set()
        for k, v in value.items():
            out |= _fact_numbers(v, k)
        return out
    if isinstance(value, (list, tuple)):
        out = set()
        for v in value:
            out |= _fact_numbers(v, key)
        return out
    if key == "window" and isinstance(value, str):
        return {float(n) for n in _NUMBER.findall(value)}
    return set()


def _registry_names() -> set[str]:
    try:
        _, entries = registry.load_registry()
    except Exception:
        return set()
    return {e.id.lower() for e in entries}


def validate_llm_text(text: dict, bundle: dict) -> bool:
    if not isinstance(text, dict):
        return False
    values = []
    for key in TEXT_FIELDS:
        value = text.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
        values.append(value)
    joined = "\n".join(values)
    dump = json.dumps(bundle, default=str, sort_keys=True)

    if not _paths(joined) <= _paths(dump):
        return False

    allowed_agents = {a["agent"].lower() for a in bundle.get("agents", []) if a.get("agent")}
    lowered = joined.lower()
    for name in _registry_names() - allowed_agents:
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", lowered):
            return False

    stripped = _PATH.sub(" ", joined)
    used = {float(n) for n in _NUMBER.findall(stripped)}
    return used <= _fact_numbers(bundle) | _FIXED_NUMBERS
