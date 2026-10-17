from datetime import datetime

from psycopg import AsyncConnection
from psycopg.rows import dict_row

VERDICT_COLUMNS = (
    "site_id",
    "client_key",
    "edge_signal",
    "user_agent",
    "client_ip",
    "claimed_agent",
    "registry_category",
    "verdict",
    "method",
    "evidence",
    "registry_version",
    "rule_version",
    "ip_snapshot_version",
    "checked_at",
    "flags",
)


async def current_verdict(
    conn: AsyncConnection, site_id: str, client_key: str, edge_signal: str
) -> dict | None:
    # Current row = highest id for (site_id, client_key, edge_signal).
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select * from verdicts
            where site_id = %s and client_key = %s and edge_signal = %s
            order by id desc limit 1
            """,
            [site_id, client_key, edge_signal],
        )
        return await cur.fetchone()


async def append_verdict(conn: AsyncConnection, row: dict) -> int:
    values = {"flags": []} | {k: v for k, v in row.items() if k in VERDICT_COLUMNS}
    columns = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    cur = await conn.execute(
        f"insert into verdicts ({columns}) values ({marks}) returning id", list(values.values())
    )
    return (await cur.fetchone())[0]


async def verdicts_without_class(conn: AsyncConnection, site_id: str) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "select * from verdicts where site_id = %s and traffic_class is null order by id",
            [site_id],
        )
        return await cur.fetchall()


async def pending_client_groups(conn: AsyncConnection, site_id: str) -> list[dict]:
    # Events with no verdict, grouped by (client_key, edge_signal). Pending pair rows are skipped.
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select client_key, edge_signal,
                   min(user_agent) as user_agent,
                   min(host(client_ip)) as client_ip,
                   min(ts) as min_ts, max(ts) as max_ts,
                   count(*) as events
            from events
            where site_id = %s and verdict_id is null
              and pair_state <> 'pending' and client_key is not null
            group by client_key, edge_signal
            order by client_key, edge_signal
            """,
            [site_id],
        )
        return await cur.fetchall()


async def assign_events_verdict(
    conn: AsyncConnection,
    site_id: str,
    client_key: str,
    edge_signal: str,
    verdict_id: int,
    min_ts: datetime,
    max_ts: datetime,
) -> int:
    # The ts bounds let Postgres prune daily partitions.
    cur = await conn.execute(
        """
        update events set verdict_id = %s
        where site_id = %s and client_key = %s and edge_signal = %s
          and verdict_id is null and pair_state <> 'pending'
          and ts between %s and %s
        """,
        [verdict_id, site_id, client_key, edge_signal, min_ts, max_ts],
    )
    return cur.rowcount
