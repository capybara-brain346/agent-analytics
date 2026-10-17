from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("")
async def list_imports() -> dict:
    raise not_implemented()


@router.post("/upload")
async def upload() -> dict:
    """Dashboard upload: same streamed path as /ingest, backfill priority, limit 2 GB (1.17)."""
    raise not_implemented()
