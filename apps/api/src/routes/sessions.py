from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("")
async def list_sessions() -> dict:
    raise not_implemented()


@router.get("/{session_id}")
async def get_session(session_id: str) -> dict:
    raise not_implemented()
