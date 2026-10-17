from datetime import datetime

from pydantic import BaseModel

from src.models.domain import Lane


class LaneHealth(BaseModel):
    site_id: str
    lane: Lane
    last_success: datetime | None
    healthy: bool


class Health(BaseModel):
    healthy: bool
    lanes: list[LaneHealth]


class IngestAccepted(BaseModel):
    file_id: str
    duplicate: bool = False
