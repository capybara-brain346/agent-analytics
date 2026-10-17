"""Routers.

`root_router` = machine paths. `api_router` = dashboard JSON under `/api` (dashboard.md §14).
"""

from fastapi import APIRouter

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

root_router = APIRouter()
root_router.include_router(health.router)
root_router.include_router(metrics.router)
root_router.include_router(ingest.router)

api_router = APIRouter()
for module in (overview, recommendations, agents, events, sessions, pages, journeys, imports, runs):
    api_router.include_router(module.router)
