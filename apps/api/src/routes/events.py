from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/events", tags=["events"])


@router.get("")
async def list_events() -> dict:
    raise not_implemented()


@router.get("/{event_id}")
async def get_event(event_id: str) -> dict:
    raise not_implemented()
