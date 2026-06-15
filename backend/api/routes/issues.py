# backend/api/routes/issues.py
"""
Issue management routes.

Endpoints:
  GET  /issues              — paginated list with filters
  GET  /issues/stats        — aggregated stats
  GET  /issues/{id}         — issue detail
  POST /issues/{id}/start-workflow — trigger agent workflow
  POST /issues/{id}/skip    — skip issue with reason
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_pagination, PaginationParams, verify_api_key
from backend.models.issue import Issue as IssueModel
from backend.models.repository import Repository as RepoModel

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_TIERS = {"SENIOR", "STAFF", "INNOVATION", "SKIP"}
VALID_STATUSES = {"open", "in_progress", "pr_created", "merged", "closed", "skipped"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class IssueListItem(BaseModel):
    id: UUID
    repo_id: UUID
    repo_full_name: Optional[str]
    number: int
    title: str
    url: str
    complexity_tier: Optional[str]
    difficulty_score: Optional[float]
    merge_probability: Optional[float]
    engagement_score: Optional[float]
    composite_score: Optional[float]
    status: str
    labels: Optional[List[str]]
    comment_count: Optional[int]
    has_open_pr: Optional[bool]
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class IssueDetail(IssueListItem):
    body: Optional[str]
    body_summary: Optional[str]
    has_stack_trace: Optional[bool]
    has_benchmark: Optional[bool]
    thread_depth: Optional[int]
    skip_reason: Optional[str]
    agent_run_id: Optional[UUID]
    last_scored_at: Optional[str]


class StartWorkflowRequest(BaseModel):
    priority: Optional[str] = Field("normal", description="normal | high | low")
    force: bool = Field(False, description="Force re-run even if already in progress")


class StartWorkflowResponse(BaseModel):
    message: str
    issue_id: UUID
    agent_run_id: Optional[UUID]
    task_id: Optional[str]


class SkipRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class SkipResponse(BaseModel):
    message: str
    issue_id: UUID
    reason: str


class IssueStats(BaseModel):
    total: int
    by_tier: Dict[str, int]
    by_status: Dict[str, int]
    by_repo: List[Dict]
    avg_composite_score: Optional[float]


class PaginatedIssues(BaseModel):
    items: List[IssueListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Background task helpers
# ---------------------------------------------------------------------------

async def _start_issue_workflow(issue_id: str, priority: str) -> None:
    """Kick off the full agent workflow for an issue."""
    try:
        from backend.core.task_queue import enqueue_task
        await enqueue_task("run_issue_workflow", {"issue_id": issue_id, "priority": priority})
        logger.info("Workflow enqueued for issue %s", issue_id)
    except Exception as exc:
        logger.error("Failed to enqueue workflow for issue %s: %s", issue_id, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedIssues, summary="List all issues")
async def list_issues(
    complexity_tier: Optional[str] = Query(None, description="SENIOR|STAFF|INNOVATION|SKIP"),
    issue_status: Optional[str] = Query(None, alias="status"),
    repo_id: Optional[UUID] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    has_open_pr: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Search in title/body"),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaginatedIssues:
    stmt = select(IssueModel)

    if complexity_tier:
        tier = complexity_tier.upper()
        if tier not in VALID_TIERS:
            raise HTTPException(status_code=422, detail=f"Invalid tier. Valid: {VALID_TIERS}")
        stmt = stmt.where(IssueModel.complexity_tier == tier)
    if issue_status:
        if issue_status not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Valid: {VALID_STATUSES}")
        stmt = stmt.where(IssueModel.status == issue_status)
    if repo_id:
        stmt = stmt.where(IssueModel.repo_id == repo_id)
    if min_score is not None:
        stmt = stmt.where(IssueModel.composite_score >= min_score)
    if has_open_pr is not None:
        stmt = stmt.where(IssueModel.has_open_pr == has_open_pr)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (IssueModel.title.ilike(pattern)) | (IssueModel.body.ilike(pattern))
        )

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total: int = count_result.scalar_one()

    stmt = stmt.order_by(IssueModel.composite_score.desc().nullslast())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    issues = result.scalars().all()

    total_pages = max(1, (total + pagination.page_size - 1) // pagination.page_size)
    return PaginatedIssues(
        items=[IssueListItem.from_orm(i) for i in issues],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
    )


@router.get("/stats", response_model=IssueStats, summary="Aggregated issue statistics")
async def get_issue_stats(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> IssueStats:
    """Return aggregated statistics across all issues."""
    # Total count
    total_result = await db.execute(select(func.count()).select_from(IssueModel))
    total: int = total_result.scalar_one()

    # By tier
    tier_result = await db.execute(
        select(IssueModel.complexity_tier, func.count(IssueModel.id))
        .group_by(IssueModel.complexity_tier)
    )
    by_tier = {row[0] or "UNKNOWN": row[1] for row in tier_result.all()}

    # By status
    status_result = await db.execute(
        select(IssueModel.status, func.count(IssueModel.id))
        .group_by(IssueModel.status)
    )
    by_status = {row[0] or "unknown": row[1] for row in status_result.all()}

    # By repo (top 10)
    repo_result = await db.execute(
        select(IssueModel.repo_id, func.count(IssueModel.id).label("count"))
        .group_by(IssueModel.repo_id)
        .order_by(func.count(IssueModel.id).desc())
        .limit(10)
    )
    by_repo = [{"repo_id": str(row[0]), "count": row[1]} for row in repo_result.all()]

    # Avg score
    avg_result = await db.execute(select(func.avg(IssueModel.composite_score)))
    avg_score = avg_result.scalar_one()

    return IssueStats(
        total=total,
        by_tier=by_tier,
        by_status=by_status,
        by_repo=by_repo,
        avg_composite_score=round(float(avg_score), 2) if avg_score else None,
    )


@router.get("/{issue_id}", response_model=IssueDetail, summary="Get issue detail")
async def get_issue(
    issue_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> IssueDetail:
    result = await db.execute(select(IssueModel).where(IssueModel.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")
    return IssueDetail.from_orm(issue)


@router.post(
    "/{issue_id}/start-workflow",
    response_model=StartWorkflowResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger agent workflow for an issue",
)
async def start_workflow(
    issue_id: UUID,
    request: StartWorkflowRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> StartWorkflowResponse:
    """Trigger the full agent workflow (plan → implement → test → PR) for an issue."""
    result = await db.execute(select(IssueModel).where(IssueModel.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    if not request.force and issue.status == "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workflow already in progress. Use force=true to restart.",
        )

    if issue.complexity_tier == "SKIP":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Issue is marked SKIP and cannot be processed.",
        )

    # Update status
    issue.status = "in_progress"
    await db.flush()

    background_tasks.add_task(_start_issue_workflow, str(issue_id), request.priority)
    return StartWorkflowResponse(
        message="Workflow triggered in background",
        issue_id=issue_id,
        agent_run_id=None,
        task_id=None,
    )


@router.post(
    "/{issue_id}/skip",
    response_model=SkipResponse,
    summary="Skip an issue",
)
async def skip_issue(
    issue_id: UUID,
    request: SkipRequest,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> SkipResponse:
    """Mark an issue as skipped and record the reason."""
    result = await db.execute(select(IssueModel).where(IssueModel.id == issue_id))
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")

    issue.status = "skipped"
    issue.skip_reason = request.reason
    await db.flush()

    return SkipResponse(
        message="Issue marked as skipped",
        issue_id=issue_id,
        reason=request.reason,
    )
