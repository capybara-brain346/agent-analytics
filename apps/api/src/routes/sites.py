from fastapi import APIRouter

from src.services.site_config import list_sites

router = APIRouter(prefix="/sites", tags=["sites"])


@router.get("", response_model=list[str])
async def get_sites() -> list[str]:
    # Site IDs from config/sites, sorted. The dashboard site picker reads them.
    return list_sites()
