# backend/api/routes/discovery.py
"""
Discovery agent management routes.

Endpoints:
  GET  /discovery/status            — agent status & last run info
  POST /discovery/trigger           — manually trigger repo discovery
  GET  /discovery/sources           — list discovery sources & their status
  PUT  /discovery/sources/{source}  — enable/disable a discovery source
  GET  /discovery/queue             — repos queued for processing
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, verify_api_key
from backend.models.repository import Repository as RepoModel
from backend.models.discovery_source import DiscoverySource as DiscoverySourceModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class DiscoveryStatus(BaseModel):
    is_running: bool
    last_run_at: Optional[datetime]
    last_run_duration_seconds: Optional[float]
    repos_discovered_last_run: Optional[int]
    total_repos_discovered: int
    next_scheduled_run: Optional[datetime]
    agent_version: str = "1.0.0"


class DiscoverySource(BaseModel):
    name: str
    display_name: str
    is_enabled: bool
    last_run_at: Optional[datetime]
    repos_found: int
    description: str

    class Config:
        from_attributes = True


class DiscoveryTriggerRequest(BaseModel):
    sources: Optional[List[str]] = Field(None, description="Specific sources to run; empty = all enabled")
    max_repos: Optional[int] = Field(None, ge=1, le=500, description="Cap on repos to ingest")


class DiscoveryTriggerResponse(BaseModel):
    message: str
    task_id: Optional[str]
    sources_triggered: List[str]


class DiscoverySourceUpdate(BaseModel):
    is_enabled: bool


class QueuedRepo(BaseModel):
    id: UUID
    full_name: str
    queued_at: Optional[datetime]
    source: Optional[str]
    quality_score: Optional[float]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# In-memory state for discovery agent status (replace with Redis in prod)
# ---------------------------------------------------------------------------

_DISCOVERY_STATE: Dict[str, Any] = {
    "is_running": False,
    "last_run_at": None,
    "last_run_duration_seconds": None,
    "repos_discovered_last_run": None,
    "next_scheduled_run": None,
}

KNOWN_SOURCES = {
    "gsoc": "Google Summer of Code",
    "cncf": "CNCF Landscape",
    "apache": "Apache Software Foundation",
    "github_trending": "GitHub Trending",
    "awesome_lists": "Awesome Lists",
}


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_discovery(sources: List[str], max_repos: Optional[int]) -> None:
    """Background task: run the repo discovery service."""
    import time
    from backend.services.repo_discovery_service import RepoDiscoveryService

    _DISCOVERY_STATE["is_running"] = True
    start = time.monotonic()
    try:
        svc = RepoDiscoveryService()
        total = 0
        for source in sources:
            try:
                if source == "gsoc":
                    repos = await svc.discover_from_gsoc()
                elif source == "cncf":
                    repos = await svc.discover_from_cncf()
                elif source == "apache":
                    repos = await svc.discover_from_apache()
                elif source == "github_trending":
                    repos = await svc.discover_from_github_trending()
                elif source == "awesome_lists":
                    repos = await svc.discover_from_awesome_lists()
                else:
                    logger.warning("Unknown discovery source: %s", source)
                    continue
                if max_repos:
                    repos = repos[: max_repos - total]
                await svc.upsert_repos(repos)
                total += len(repos)
                logger.info("Discovery source '%s' returned %d repos", source, len(repos))
                if max_repos and total >= max_repos:
                    break
            except Exception as exc:
                logger.error("Discovery source '%s' failed: %s", source, exc)

        _DISCOVERY_STATE["repos_discovered_last_run"] = total
    finally:
        _DISCOVERY_STATE["is_running"] = False
        _DISCOVERY_STATE["last_run_at"] = datetime.utcnow()
        _DISCOVERY_STATE["last_run_duration_seconds"] = round(time.monotonic() - start, 2)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/status", response_model=DiscoveryStatus, summary="Discovery agent status")
async def get_discovery_status(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> DiscoveryStatus:
    """Return current discovery agent status and statistics."""
    count_result = await db.execute(select(func.count()).select_from(RepoModel))
    total_repos: int = count_result.scalar_one()

    return DiscoveryStatus(
        is_running=_DISCOVERY_STATE["is_running"],
        last_run_at=_DISCOVERY_STATE["last_run_at"],
        last_run_duration_seconds=_DISCOVERY_STATE["last_run_duration_seconds"],
        repos_discovered_last_run=_DISCOVERY_STATE["repos_discovered_last_run"],
        total_repos_discovered=total_repos,
        next_scheduled_run=_DISCOVERY_STATE["next_scheduled_run"],
    )


@router.post(
    "/trigger",
    response_model=DiscoveryTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger repository discovery",
)
async def trigger_discovery(
    request: DiscoveryTriggerRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> DiscoveryTriggerResponse:
    """Enqueue a discovery run for the specified (or all enabled) sources."""
    if _DISCOVERY_STATE["is_running"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Discovery is already running. Wait for it to complete.",
        )

    # Determine which sources to run
    if request.sources:
        unknown = [s for s in request.sources if s not in KNOWN_SOURCES]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown sources: {unknown}. Valid: {list(KNOWN_SOURCES.keys())}",
            )
        sources_to_run = request.sources
    else:
        # All enabled sources
        try:
            result = await db.execute(
                select(DiscoverySourceModel).where(DiscoverySourceModel.is_enabled == True)  # noqa: E712
            )
            enabled = [r.name for r in result.scalars().all()]
            sources_to_run = enabled if enabled else list(KNOWN_SOURCES.keys())
        except Exception:
            sources_to_run = list(KNOWN_SOURCES.keys())

    background_tasks.add_task(_run_discovery, sources_to_run, request.max_repos)
    return DiscoveryTriggerResponse(
        message="Discovery triggered in background",
        task_id=None,
        sources_triggered=sources_to_run,
    )


@router.get("/sources", response_model=List[DiscoverySource], summary="List discovery sources")
async def list_sources(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[DiscoverySource]:
    """Return all discovery sources and their enabled/disabled status."""
    try:
        result = await db.execute(select(DiscoverySourceModel))
        db_sources = {r.name: r for r in result.scalars().all()}
    except Exception:
        db_sources = {}

    sources = []
    for key, display in KNOWN_SOURCES.items():
        db_src = db_sources.get(key)
        sources.append(
            DiscoverySource(
                name=key,
                display_name=display,
                is_enabled=db_src.is_enabled if db_src else True,
                last_run_at=db_src.last_run_at if db_src else None,
                repos_found=db_src.repos_found if db_src else 0,
                description=f"Discover repos from {display}",
            )
        )
    return sources


@router.put("/sources/{source}", response_model=DiscoverySource, summary="Enable/disable a discovery source")
async def update_source(
    source: str = Path(..., description="Source name"),
    payload: DiscoverySourceUpdate = ...,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> DiscoverySource:
    """Enable or disable a specific discovery source."""
    if source not in KNOWN_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown source '{source}'. Valid: {list(KNOWN_SOURCES.keys())}",
        )
    try:
        result = await db.execute(
            select(DiscoverySourceModel).where(DiscoverySourceModel.name == source)
        )
        db_src = result.scalar_one_or_none()
        if db_src:
            db_src.is_enabled = payload.is_enabled
        else:
            db_src = DiscoverySourceModel(
                name=source,
                is_enabled=payload.is_enabled,
                repos_found=0,
            )
            db.add(db_src)
        await db.flush()
        return DiscoverySource(
            name=source,
            display_name=KNOWN_SOURCES[source],
            is_enabled=db_src.is_enabled,
            last_run_at=db_src.last_run_at if hasattr(db_src, "last_run_at") else None,
            repos_found=db_src.repos_found,
            description=f"Discover repos from {KNOWN_SOURCES[source]}",
        )
    except Exception as exc:
        logger.error("Failed to update source %s: %s", source, exc)
        raise HTTPException(status_code=500, detail="Failed to update source configuration")


@router.get("/queue", response_model=List[QueuedRepo], summary="Repos queued for processing")
async def get_queue(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[QueuedRepo]:
    """Return repositories that are queued/pending analysis."""
    stmt = (
        select(RepoModel)
        .where(RepoModel.last_analyzed_at == None)  # noqa: E711
        .order_by(RepoModel.quality_score.desc().nullslast())
        .limit(limit)
    )
    result = await db.execute(stmt)
    repos = result.scalars().all()
    return [
        QueuedRepo(
            id=r.id,
            full_name=r.full_name,
            queued_at=r.created_at,
            source=getattr(r, "discovery_source", None),
            quality_score=r.quality_score,
        )
        for r in repos
    ]
