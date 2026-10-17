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
    """Streamed body → inbox, 64 KB parts, no parsing (decision 1.15).

    202 = stored; 200 = duplicate chunk; 401 = bad site token; 413 = over 50 MB; 429 = over quota.
    """
    raise not_implemented()
