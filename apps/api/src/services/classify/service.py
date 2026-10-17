from psycopg import AsyncConnection

from src.services.classify.rules import RULE_VERSION, classify
from src.services.classify.ua import ua_type
from src.store import classify as store


async def classify_new_verdicts(conn: AsyncConnection, site_id: str) -> dict:
    pending = await store.fetch_unclassified(conn, site_id)
    rows = []
    for v in pending:
        ut = ua_type(v["user_agent"])
        c = classify(v["verdict"], v["registry_category"], ut, v["edge_signal"])
        rows.append(
            (
                c.traffic_class,
                c.confidence,
                c.rule_id,
                RULE_VERSION,
                c.evidence,
                str(ut),
                c.flags,
                v["id"],
            )
        )
    saved = await store.save_classes(conn, rows)
    return {"classified": saved}
