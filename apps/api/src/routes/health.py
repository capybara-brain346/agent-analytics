from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from src.config import get_settings
from src.logger import get_logger
from src.models.api import Health, LaneHealth
from src.models.domain import Lane
from src.services import pipeline
from src.services.site_config import list_sites
from src.store import alerts, db, runs

log = get_logger(__name__)

router = APIRouter(tags=["health"])


class HealthAlert(BaseModel):
    id: int
    site_id: str
    kind: str
    source: str | None
    message: str
    raised_at: datetime


class HealthReport(Health):
    alerts: list[HealthAlert]


def stale_after(lane: Lane) -> timedelta:
    # The slow lane runs once for each window, so it may be silent that long plus the margin (7.6).
    settings = get_settings()
    margin = timedelta(minutes=settings.health_stale_minutes)
    if lane == Lane.SLOW:
        return pipeline.slow_interval(settings.recommendation_window) + margin
    return margin


@router.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health", responses={503: {"model": HealthReport}})
async def health(response: Response) -> HealthReport:
    now = datetime.now(UTC)
    try:
        async with db.connection() as conn:
            last = {(r["site_id"], r["lane"]): r["last_success"]
                    for r in await runs.last_success_by_lane(conn, list_sites())}  # fmt: skip
            open_alerts = await alerts.list_alerts(conn, open_only=True, limit=100)
    except Exception:
        log.exception("health check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthReport(healthy=False, lanes=[], alerts=[])
    lanes = []
    for site_id in list_sites():
        for lane in Lane:
            seen = last.get((site_id, lane.value))
            lanes.append(
                LaneHealth(
                    site_id=site_id,
                    lane=lane,
                    last_success=seen,
                    healthy=seen is not None and now - seen <= stale_after(lane),
                )
            )
    healthy = all(x.healthy for x in lanes)
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthReport(
        healthy=healthy,
        lanes=lanes,
        alerts=[HealthAlert.model_validate(a, from_attributes=False) for a in open_alerts],
    )
