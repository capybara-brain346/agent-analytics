from psycopg import AsyncConnection

RULE_VERSION = "1"


async def classify_new_verdicts(conn: AsyncConnection, site_id: str) -> dict:
    raise NotImplementedError
