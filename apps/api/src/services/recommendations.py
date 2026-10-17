"""Flow 5 · Recommendation engine.

patterns (SQL) → candidates → score → fact bundle → LLM text → validator → template fallback.
"""

from psycopg import AsyncConnection

from src.models.domain import Pattern


async def generate(conn: AsyncConnection, site_id: str, window: str) -> str:
    """Run all patterns for the window, store one append-only run. Return run ID."""
    raise NotImplementedError


def score(impact: int, frequency: int, severity: int, confidence: float) -> float:
    return impact * frequency * severity * confidence


def template_text(pattern: Pattern, bundle: dict) -> dict:
    """Fallback text for the 4 LLM fields (decision 5.9)."""
    raise NotImplementedError


def validate_llm_text(text: dict, bundle: dict) -> bool:
    """Every number, path and agent name must be in the bundle (decision 5.8)."""
    raise NotImplementedError
