from typing import Annotated

from fastapi import APIRouter, Query

from src.routes.errors import not_implemented

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
async def get_overview(
    site: str | None = None,
    from_: Annotated[str | None, Query(alias="from")] = None,
    to: str | None = None,
    traffic_class: Annotated[int | None, Query(alias="class")] = None,
) -> dict:
    raise not_implemented()
