from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/pages", tags=["pages"])


@router.get("")
async def list_pages(path: str | None = None) -> dict:
    raise not_implemented()
