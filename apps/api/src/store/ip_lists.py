from psycopg import AsyncConnection
from psycopg.rows import dict_row


async def save_snapshot(
    conn: AsyncConnection, source: str, version: str, prefixes: list[str]
) -> bool:
    # False when (source, version) already exists.
    cur = await conn.execute(
        """
        insert into ip_list_snapshots (source, version, prefixes)
        values (%s, %s, %s::cidr[])
        on conflict (source, version) do nothing
        """,
        [source, version, prefixes],
    )
    return cur.rowcount == 1


async def latest_snapshot(conn: AsyncConnection, source: str) -> dict | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            select source, version, fetched_at, prefixes from ip_list_snapshots
            where source = %s order by fetched_at desc, version desc limit 1
            """,
            [source],
        )
        return await cur.fetchone()


async def latest_versions(conn: AsyncConnection) -> dict[str, str]:
    cur = await conn.execute(
        """
        select distinct on (source) source, version from ip_list_snapshots
        order by source, fetched_at desc, version desc
        """
    )
    return {source: version for source, version in await cur.fetchall()}


async def ip_in_prefixes(conn: AsyncConnection, source: str, version: str, ip: str) -> bool:
    cur = await conn.execute(
        """
        select exists (
            select 1 from ip_list_snapshots, unnest(prefixes) as p
            where source = %s and version = %s and %s::inet <<= p
        )
        """,
        [source, version, ip],
    )
    return (await cur.fetchone())[0]
