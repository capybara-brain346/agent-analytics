from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("")
async def list_recommendations(run: str | None = None) -> dict:
    raise not_implemented()


@router.post("/generate")
async def generate_now(site: str) -> dict:
    raise not_implemented()


@router.get("/{rec_id}")
async def get_recommendation(rec_id: str) -> dict:
    raise not_implemented()
