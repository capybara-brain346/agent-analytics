from psycopg import AsyncConnection
from psycopg.rows import dict_row

from src.models.domain import AlertKind


async def raise_alert(
    conn: AsyncConnection, site_id: str, kind: AlertKind, source: str | None, message: str
) -> int | None:
    # None when the same alert (site, kind, source) is already open.
    cur = await conn.execute(
        """
        insert into alerts (site_id, kind, source, message) values (%s, %s, %s, %s)
        on conflict do nothing returning id
        """,
        [site_id, AlertKind(kind).value, source, message],
    )
    row = await cur.fetchone()
    return row[0] if row else None


async def resolve_alert(
    conn: AsyncConnection, site_id: str, kind: AlertKind, source: str | None
) -> bool:
    cur = await conn.execute(
        """
        update alerts set resolved_at = now()
        where site_id = %s and kind = %s and coalesce(source, '') = coalesce(%s, '')
          and resolved_at is null
        """,
        [site_id, AlertKind(kind).value, source],
    )
    return cur.rowcount > 0


async def list_alerts(
    conn: AsyncConnection, site_id: str | None = None, open_only: bool = False, limit: int = 50
) -> list[dict]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select * from alerts
            where (%s::text is null or site_id = %s) and (not %s or resolved_at is null)
            order by raised_at desc, id desc
            limit %s
            """,
            [site_id, site_id, open_only, limit],
        )
        return await cur.fetchall()
