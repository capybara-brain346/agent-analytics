from datetime import datetime

from psycopg import AsyncConnection

# Derived tables: each entry is (table, delete condition on the cutoff). Raw `events` partitions
# are dropped by cleanup; these rows are rebuilt from events, so they follow the same horizon.
_PRUNE = {
    "page_stats": "hour < %(cutoff)s",
    "journey_steps": "hour < %(cutoff)s",
    "agents": "hour < %(cutoff)s",
    "session_events": "event_ts < %(cutoff)s",
    "sessions": "last_seen < %(cutoff)s",
    "pipeline_runs": "started_at < %(cutoff)s and status <> 'running'",
    "import_rejects": ("file_id in (select id from import_files where received_at < %(cutoff)s)"),
}


async def prune_older_than(conn: AsyncConnection, cutoff: datetime) -> dict[str, int]:
    counts = {}
    for table, condition in _PRUNE.items():
        cur = await conn.execute(f"delete from {table} where {condition}", {"cutoff": cutoff})
        counts[table] = cur.rowcount
    return counts
