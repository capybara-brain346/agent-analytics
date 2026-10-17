"""Flow 4 view tables: sessions, open_sessions, session_events, page_stats, journey_steps, agents.

Window-function SQL lives here. Rows are written as "newest version of row X" (decision S.4).
All writes for one site run in one transaction (L3, decision 4.7).
"""

from psycopg import AsyncConnection


async def update_open_sessions(conn: AsyncConnection, site_id: str) -> None:
    raise NotImplementedError


async def close_idle_sessions(conn: AsyncConnection, site_id: str) -> None:
    raise NotImplementedError


async def update_current_hour(conn: AsyncConnection, site_id: str) -> None:
    raise NotImplementedError


async def recompute_range(conn: AsyncConnection, site_id: str, client_key: str) -> None:
    """Late events for a closed range: delete + insert in one transaction (decision 4.6)."""
    raise NotImplementedError
