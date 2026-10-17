from fastapi import APIRouter

from src.routes.errors import not_implemented

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
async def list_agents() -> dict:
    raise not_implemented()


@router.get("/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    raise not_implemented()
