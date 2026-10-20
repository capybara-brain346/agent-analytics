from src.config import get_settings

SEVERITY = {"P1": 2, "P2": 3, "P3": 3, "P4": 2, "P5": 2}
CONFIDENCE_FACTOR = {"high": 1.0, "medium": 0.6, "low": 0.3}
CONFIDENCE_WHY = {
    "high": "verified identity, IP not shared",
    "medium": "claimed identity or browser, IP not shared",
    "low": "agent client, shared IP, or unknown class",
}
LEVELS = ("low", "medium", "high")


def score(impact: int, frequency: int, severity: int, confidence: float) -> float:
    return impact * frequency * severity * confidence


def frequency_factor(sessions: int) -> int:
    settings = get_settings()
    if sessions < settings.frequency_mid_min:
        return 1
    if sessions <= settings.frequency_high_over:
        return 2
    return 3


def confidence_label(n_high: int, n_medium: int, n_low: int) -> str:
    # Most evidence sessions decide. A tie goes to the lower level. No sessions = low.
    counts = {"low": n_low, "medium": n_medium, "high": n_high}
    top = max(counts.values())
    if top == 0:
        return "low"
    return next(label for label, n in counts.items() if n == top)


def evidence_cap(pattern: str, kind: str | None) -> tuple[str, str]:
    key = f"{pattern}:{kind}" if kind else pattern
    return key, get_settings().confidence_cap.get(key, "high")


def factors(
    pattern: str,
    kind: str | None,
    target: str,
    is_key_page: bool,
    sessions: int,
    n_high: int,
    n_medium: int,
    n_low: int,
) -> dict:
    identity = confidence_label(n_high, n_medium, n_low)
    cap_key, cap = evidence_cap(pattern, kind)
    label = min(identity, cap, key=LEVELS.index)
    impact = 3 if is_key_page else 1
    frequency = frequency_factor(sessions)
    severity = SEVERITY[pattern]
    factor = CONFIDENCE_FACTOR[label]
    total = n_high + n_medium + n_low
    return {
        "impact": impact,
        "frequency": frequency,
        "severity": severity,
        "confidence_factor": factor,
        "confidence": label,
        "score": score(impact, frequency, severity, factor),
        "factor_reasons": {
            "impact": (
                f"Impact {impact}: {target} is a key or conversion page"
                if is_key_page
                else f"Impact {impact}: {target} is not a key or conversion page"
            ),
            "frequency": f"Frequency {frequency}: {sessions} sessions affected",
            "severity": f"Severity {severity}: fixed for pattern {pattern}",
            "confidence": (
                f"Confidence {factor}: {label}, the lower of identity {identity} "
                f"({CONFIDENCE_WHY[identity]}; {n_high} high, {n_medium} medium, {n_low} low "
                f"of {total} sessions) and evidence cap {cap} for {cap_key}"
            ),
        },
    }
