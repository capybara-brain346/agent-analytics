from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/journeys", tags=["journeys"])


@router.get("")
async def list_journeys() -> dict:
    raise not_implemented()


@router.get("/{journey_id}")
async def get_journey(journey_id: str) -> dict:
    raise not_implemented()
