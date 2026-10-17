from fastapi import APIRouter

from src.models.api import Health
from src.routes.errors import not_implemented

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez() -> dict[str, str]:
    """Process is up. Kubernetes liveness probe; no database call."""
    return {"status": "ok"}


@router.get("/health")
async def health() -> Health:
    """Last success of each site + lane; > 15 min = unhealthy (decisions 7.6, 7.11)."""
    raise not_implemented()
