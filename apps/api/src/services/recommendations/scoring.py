def score(impact: int, frequency: int, severity: int, confidence: float) -> float:
    return impact * frequency * severity * confidence
