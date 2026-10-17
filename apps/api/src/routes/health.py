from fastapi import APIRouter

from src.models.api import Health
from src.routes.errors import not_implemented

router = APIRouter(tags=["health"])


@router.get("/livez")
async def livez() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health")
async def health() -> Health:
    raise not_implemented()
