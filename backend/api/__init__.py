# backend/api/__init__.py
"""
API package for OpenSource AI Engineer.
Exposes the main FastAPI router that aggregates all sub-routers.
"""
from fastapi import APIRouter

from backend.api.routes import (
    repositories,
    discovery,
    issues,
    agent_runs,
    pull_requests,
    analytics,
    settings,
    notifications,
    innovation,
    webhooks,
    feedback,
)

api_router = APIRouter()

api_router.include_router(repositories.router, prefix="/repositories", tags=["repositories"])
api_router.include_router(discovery.router, prefix="/discovery", tags=["discovery"])
api_router.include_router(issues.router, prefix="/issues", tags=["issues"])
api_router.include_router(agent_runs.router, prefix="/agent-runs", tags=["agent-runs"])
api_router.include_router(pull_requests.router, prefix="/pull-requests", tags=["pull-requests"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(innovation.router, prefix="/innovation", tags=["innovation"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
api_router.include_router(feedback.router, prefix="/feedback", tags=["feedback"])

__all__ = ["api_router"]
