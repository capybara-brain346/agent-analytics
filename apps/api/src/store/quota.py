from datetime import datetime, timedelta

from psycopg import AsyncConnection


async def bytes_received_last_day(conn: AsyncConnection, site_id: str, now: datetime) -> int:
    # The byte quota of /ingest (1.16). Read from Postgres, so all API replicas share it. Uploads,
    # CLI files and bucket copies are not /ingest calls: they do not count.
    cur = await conn.execute(
        "select coalesce(sum(size_bytes), 0) from import_files "
        "where site_id = %s and entry = 'ingest' and received_at > %s",
        [site_id, now - timedelta(days=1)],
    )
    return int((await cur.fetchone())[0])
