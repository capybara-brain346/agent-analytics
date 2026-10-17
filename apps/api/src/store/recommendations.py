"""Recommendation runs and items, append-only with rule_version (decision 5.4)."""

from psycopg import AsyncConnection


async def save_run(conn: AsyncConnection, site_id: str, window: str, items: list[dict]) -> str:
    raise NotImplementedError


async def cached_text(conn: AsyncConnection, bundle_hash: str) -> dict | None:
    """LLM text cached by hash(bundle) (decision 5.10)."""
    raise NotImplementedError
