from fastapi import APIRouter

from src.models.api import CLASS_NAMES, JourneyClassRow, JourneyOut, LabeledText
from src.routes.params import Conn, ScopeDep, not_found
from src.services import site_config
from src.store import queries

router = APIRouter(prefix="/journeys", tags=["journeys"])


async def build(conn, scope, only: str | None = None) -> list[JourneyOut]:
    cfg = site_config.load_site_config(scope.site_id)
    rows = await queries.list_journeys(conn, scope.filters())
    out = []
    for j in cfg.journeys:
        if only and j.id != only:
            continue
        n = len(j.steps)
        classes: dict[int, dict] = {}
        for r in rows:
            if r["journey_id"] != j.id or r["traffic_class"] is None:
                continue
            c = classes.setdefault(r["traffic_class"], {"highest": [0] * (n + 1), "retry": [0] * n})
            if r["kind"] == "reached":
                c["highest"][min(r["highest"], n)] += r["sessions"]
            elif 1 <= r["step_no"] <= n:
                c["retry"][r["step_no"] - 1] += r["retry_or_loop"]
        by_class = []
        for tc, c in sorted(classes.items()):
            highest = c["highest"]
            # reached[k] = sessions whose highest step is k+1 or more
            reached = [sum(highest[k + 1 :]) for k in range(n)]
            by_class.append(
                JourneyClassRow(
                    traffic_class=tc,
                    class_name=CLASS_NAMES[tc],
                    sessions=reached[0] if reached else 0,
                    reached=reached,
                    stopped_at=highest[1:],
                    retry_or_loop=c["retry"],
                )
            )
        out.append(
            JourneyOut(
                journey_id=j.id,
                critical=j.critical,
                steps=j.steps,
                by_class=by_class,
                outcome=LabeledText(
                    text="Outcome: Unknown - logs cannot show task completion", label="unknown"
                ),
            )
        )
    return out


@router.get("", response_model=list[JourneyOut])
async def list_journeys(conn: Conn, scope: ScopeDep) -> list[JourneyOut]:
    return await build(conn, scope)


@router.get("/{journey_id}", response_model=JourneyOut)
async def get_journey(conn: Conn, scope: ScopeDep, journey_id: str) -> JourneyOut:
    found = await build(conn, scope, journey_id)
    if not found:
        raise not_found("journey", journey_id)
    return found[0]
