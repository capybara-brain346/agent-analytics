from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def list_runs() -> dict:
    raise not_implemented()
