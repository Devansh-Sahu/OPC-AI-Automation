# backend/api/routes/innovation.py
"""
Innovation / RFC proposal routes.

Endpoints:
  GET  /innovation                    — list all RFC proposals
  GET  /innovation/{id}               — RFC detail
  GET  /innovation/backlog/{repo_id}  — improvement backlog for a repo
  POST /innovation/{repo_id}/trigger  — trigger innovation analysis
  POST /innovation/{id}/approve       — approve RFC for implementation
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_pagination, PaginationParams, verify_api_key
from backend.models.innovation import InnovationProposal as ProposalModel
from backend.models.repository import Repository as RepoModel

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_RFC_STATUSES = {"draft", "approved", "in_progress", "implemented", "rejected"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RFCListItem(BaseModel):
    id: UUID
    repo_id: UUID
    repo_full_name: Optional[str]
    title: str
    category: Optional[str]
    estimated_impact: Optional[str]
    rfc_status: str
    created_at: Optional[datetime]
    approved_at: Optional[datetime]

    class Config:
        from_attributes = True


class RFCDetail(RFCListItem):
    problem_statement: Optional[str]
    proposed_solution: Optional[str]
    implementation_plan: Optional[str]
    affected_files: Optional[List[str]]
    estimated_complexity: Optional[str]
    estimated_lines_changed: Optional[int]
    approval_notes: Optional[str]
    rejection_reason: Optional[str]
    agent_run_id: Optional[UUID]


class BacklogItem(BaseModel):
    id: UUID
    repo_id: UUID
    title: str
    description: Optional[str]
    category: str
    priority: int
    estimated_effort: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class TriggerInnovationRequest(BaseModel):
    focus_areas: Optional[List[str]] = Field(
        None,
        description="Optional list of focus areas: performance, security, testing, documentation, refactoring",
    )
    max_proposals: int = Field(5, ge=1, le=20)


class TriggerInnovationResponse(BaseModel):
    message: str
    repo_id: UUID
    task_id: Optional[str]


class ApproveRFCRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=2000)


class ApproveRFCResponse(BaseModel):
    message: str
    rfc_id: UUID
    task_id: Optional[str]


class PaginatedRFCs(BaseModel):
    items: List[RFCListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _run_innovation_analysis(repo_id: str, focus_areas: Optional[List[str]], max_proposals: int) -> None:
    try:
        from backend.core.task_queue import enqueue_task
        await enqueue_task(
            "run_innovation_analysis",
            {"repo_id": repo_id, "focus_areas": focus_areas or [], "max_proposals": max_proposals},
        )
        logger.info("Innovation analysis enqueued for repo %s", repo_id)
    except Exception as exc:
        logger.error("Failed to enqueue innovation analysis for repo %s: %s", repo_id, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedRFCs, summary="List all RFC proposals")
async def list_rfcs(
    rfc_status: Optional[str] = Query(None, alias="status"),
    repo_id: Optional[UUID] = Query(None),
    category: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaginatedRFCs:
    stmt = select(ProposalModel)

    if rfc_status:
        if rfc_status not in VALID_RFC_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Valid: {VALID_RFC_STATUSES}")
        stmt = stmt.where(ProposalModel.rfc_status == rfc_status)
    if repo_id:
        stmt = stmt.where(ProposalModel.repo_id == repo_id)
    if category:
        stmt = stmt.where(ProposalModel.category.ilike(f"%{category}%"))

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total: int = count_result.scalar_one()

    stmt = stmt.order_by(ProposalModel.created_at.desc().nullslast())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    proposals = result.scalars().all()

    total_pages = max(1, (total + pagination.page_size - 1) // pagination.page_size)
    return PaginatedRFCs(
        items=[RFCListItem.from_orm(p) for p in proposals],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
    )


@router.get("/backlog/{repo_id}", response_model=List[BacklogItem], summary="Improvement backlog for a repo")
async def get_repo_backlog(
    repo_id: UUID,
    category: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[BacklogItem]:
    """Return improvement backlog items for a specific repository."""
    # Verify repo exists
    repo_result = await db.execute(select(RepoModel).where(RepoModel.id == repo_id))
    if not repo_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    # Backlog = draft proposals for this repo, ordered by priority
    stmt = (
        select(ProposalModel)
        .where(ProposalModel.repo_id == repo_id)
        .where(ProposalModel.rfc_status == "draft")
    )
    if category:
        stmt = stmt.where(ProposalModel.category.ilike(f"%{category}%"))
    stmt = stmt.order_by(ProposalModel.created_at.desc()).limit(limit)

    result = await db.execute(stmt)
    proposals = result.scalars().all()

    return [
        BacklogItem(
            id=p.id,
            repo_id=p.repo_id,
            title=p.title,
            description=getattr(p, "problem_statement", None),
            category=p.category or "general",
            priority=getattr(p, "priority", 5),
            estimated_effort=getattr(p, "estimated_complexity", None),
            created_at=p.created_at,
        )
        for p in proposals
    ]


@router.get("/{rfc_id}", response_model=RFCDetail, summary="Get RFC detail")
async def get_rfc(
    rfc_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> RFCDetail:
    result = await db.execute(select(ProposalModel).where(ProposalModel.id == rfc_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFC not found")
    return RFCDetail.from_orm(proposal)


@router.post(
    "/{repo_id}/trigger",
    response_model=TriggerInnovationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger innovation analysis for a repo",
)
async def trigger_innovation(
    repo_id: UUID,
    request: TriggerInnovationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> TriggerInnovationResponse:
    """Kick off an AI-driven innovation/RFC generation analysis for a repository."""
    repo_result = await db.execute(select(RepoModel).where(RepoModel.id == repo_id))
    repo = repo_result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    background_tasks.add_task(
        _run_innovation_analysis,
        str(repo_id),
        request.focus_areas,
        request.max_proposals,
    )
    return TriggerInnovationResponse(
        message="Innovation analysis triggered in background",
        repo_id=repo_id,
        task_id=None,
    )


@router.post(
    "/{rfc_id}/approve",
    response_model=ApproveRFCResponse,
    summary="Approve RFC for implementation",
)
async def approve_rfc(
    rfc_id: UUID,
    request: ApproveRFCRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ApproveRFCResponse:
    """Approve an RFC draft for implementation — triggers the agent workflow."""
    result = await db.execute(select(ProposalModel).where(ProposalModel.id == rfc_id))
    proposal = result.scalar_one_or_none()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFC not found")

    if proposal.rfc_status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"RFC is '{proposal.rfc_status}', not draft",
        )

    proposal.rfc_status = "approved"
    proposal.approved_at = datetime.utcnow()
    proposal.approval_notes = request.notes
    await db.flush()

    # Enqueue implementation workflow
    try:
        from backend.core.task_queue import enqueue_task
        await enqueue_task("implement_rfc", {"rfc_id": str(rfc_id), "repo_id": str(proposal.repo_id)})
    except Exception as exc:
        logger.error("Failed to enqueue RFC implementation for %s: %s", rfc_id, exc)

    return ApproveRFCResponse(
        message="RFC approved and implementation workflow triggered",
        rfc_id=rfc_id,
        task_id=None,
    )
