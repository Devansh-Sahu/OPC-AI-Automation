# backend/api/deps.py
"""
Shared FastAPI dependencies for OpenSource AI Engineer.
Provides DB sessions, current-user resolution, pagination helpers, and service singletons.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings as app_settings
from backend.core.database import AsyncSessionLocal
from backend.services.github_service import GitHubService
from backend.services.cost_tracker import CostTracker
from backend.services.secrets_manager import SecretsManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session and ensure it is closed after use."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginationParams:
    """Common pagination query-parameter dependency."""

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(20, ge=1, le=200, description="Items per page"),
    ) -> None:
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
        self.limit = page_size

    def as_dict(self) -> dict:
        return {"page": self.page, "page_size": self.page_size, "offset": self.offset, "limit": self.limit}


def get_pagination(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=200, description="Items per page"),
) -> PaginationParams:
    return PaginationParams(page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# API key / auth (simple token check; swap for OAuth later)
# ---------------------------------------------------------------------------

async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """
    Validate the API key passed in X-API-Key header.
    If no API key is configured in settings, all requests are allowed (dev mode).
    """
    configured_key = app_settings.API_SECRET_KEY
    if not configured_key:
        # Dev/open mode — no key required
        return "anonymous"
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    if x_api_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return x_api_key


# ---------------------------------------------------------------------------
# Service singletons
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_secrets_manager() -> SecretsManager:
    return SecretsManager()


@lru_cache(maxsize=1)
def _get_cost_tracker() -> CostTracker:
    return CostTracker()


def get_secrets_manager() -> SecretsManager:
    return _get_secrets_manager()


def get_cost_tracker() -> CostTracker:
    return _get_cost_tracker()


def get_github_service(
    secrets: SecretsManager = Depends(get_secrets_manager),
) -> GitHubService:
    """Return a GitHubService initialised with the stored GitHub token."""
    token = secrets.get_secret("GITHUB_TOKEN") or app_settings.GITHUB_TOKEN
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub token not configured. Add it via /settings.",
        )
    return GitHubService(token=token)


# ---------------------------------------------------------------------------
# Webhook signature helper (used by webhooks route as a dependency)
# ---------------------------------------------------------------------------

def get_webhook_secret(secrets: SecretsManager = Depends(get_secrets_manager)) -> str:
    """Return the GitHub webhook secret."""
    secret = secrets.get_secret("GITHUB_WEBHOOK_SECRET") or app_settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub webhook secret not configured.",
        )
    return secret
