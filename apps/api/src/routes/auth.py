import hmac
from typing import Annotated

from fastapi import Header, HTTPException, status

from src.config import get_settings


def bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


async def require_api_token(authorization: Annotated[str | None, Header()] = None) -> None:
    # Guards /api/*. /ingest has per-site tokens; /health and /metrics stay open for probes.
    expected = get_settings().api_token
    if not expected:
        return
    given = bearer(authorization)
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Bad token", headers={"WWW-Authenticate": "Bearer"}
        )
