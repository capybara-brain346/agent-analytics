from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("")
async def list_imports() -> dict:
    raise not_implemented()


@router.post("/upload")
async def upload() -> dict:
    raise not_implemented()
