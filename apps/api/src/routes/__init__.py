from fastapi import APIRouter, Depends

from src.routes import (
    agents,
    events,
    health,
    imports,
    ingest,
    journeys,
    metrics,
    overview,
    pages,
    recommendations,
    runs,
    sessions,
)
from src.routes.auth import require_api_token

root_router = APIRouter()
root_router.include_router(health.router)
root_router.include_router(metrics.router)
root_router.include_router(ingest.router)

api_router = APIRouter(dependencies=[Depends(require_api_token)])
for module in (overview, recommendations, agents, events, sessions, pages, journeys, imports, runs):
    api_router.include_router(module.router)
