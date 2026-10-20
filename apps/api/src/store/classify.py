from psycopg import AsyncConnection
from psycopg.rows import dict_row


async def fetch_unclassified(conn: AsyncConnection, site_id: str) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select id, user_agent, registry_category, verdict, edge_signal
            from verdicts where site_id = %s and traffic_class is null order by id
            """,
            (site_id,),
        )
        return await cur.fetchall()


async def save_classes(conn: AsyncConnection, rows: list[tuple]) -> int:
    # rows: (traffic_class, confidence, rule_id, rule_version, class_evidence, ua_type, flags, id)
    # WHERE traffic_class IS NULL: a classified row is never overwritten (decision 3.4).
    if not rows:
        return 0
    async with conn.cursor() as cur:
        await cur.executemany(
            """
            update verdicts set traffic_class = %s, confidence = %s, rule_id = %s,
                rule_version = %s, class_evidence = %s, ua_type = %s,
                flags = (select coalesce(array_agg(distinct f), '{}')
                         from unnest(flags || %s::text[]) f),
                classified_at = now()
            where id = %s and traffic_class is null
            """,
            rows,
        )
        return cur.rowcount if cur.rowcount >= 0 else len(rows)


async def save_class(
    conn: AsyncConnection,
    verdict_id: int,
    traffic_class: int,
    confidence: str,
    rule_id: str,
    rule_version: str,
    class_evidence: str,
    ua_type: str | None,
    flags: list[str],
) -> None:
    await save_classes(
        conn,
        [
            (
                traffic_class,
                confidence,
                rule_id,
                rule_version,
                class_evidence,
                ua_type,
                flags,
                verdict_id,
            )
        ],
    )


async def classified_summary(conn: AsyncConnection, site_id: str) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select traffic_class, count(*) as verdicts from verdicts
            where site_id = %s and traffic_class is not null
            group by traffic_class order by traffic_class
            """,
            (site_id,),
        )
        return await cur.fetchall()
