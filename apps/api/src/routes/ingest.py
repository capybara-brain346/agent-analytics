from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, status

from src.models.api import IngestAccepted
from src.routes.errors import not_implemented

router = APIRouter(tags=["ingest"])


@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    request: Request,
    site: Annotated[str, Query()],
    authorization: Annotated[str, Header()],
) -> IngestAccepted:
    raise not_implemented()
