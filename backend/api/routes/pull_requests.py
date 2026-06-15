# backend/api/routes/pull_requests.py
"""
Pull request management routes.

Endpoints:
  GET  /pull-requests          — list with filters
  GET  /pull-requests/pending  — PRs awaiting approval
  GET  /pull-requests/stats    — merge/acceptance rate charts
  GET  /pull-requests/{id}     — PR detail
  POST /pull-requests/{id}/approve — approve draft PR
  POST /pull-requests/{id}/reject  — reject draft PR
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_pagination, PaginationParams, get_github_service, verify_api_key
from backend.models.pull_request import PullRequest as PRModel
from backend.services.github_service import GitHubService

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_PR_STATUSES = {"draft", "open", "merged", "closed", "approved", "rejected"}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PRListItem(BaseModel):
    id: UUID
    repo_id: Optional[UUID]
    repo_full_name: Optional[str]
    issue_id: Optional[UUID]
    issue_number: Optional[int]
    pr_number: Optional[int]
    title: str
    url: Optional[str]
    pr_status: str
    merge_probability: Optional[float]
    is_draft: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    merged_at: Optional[datetime]
    agent_run_id: Optional[UUID]

    class Config:
        from_attributes = True


class PRDetail(PRListItem):
    body: Optional[str]
    head_branch: Optional[str]
    base_branch: Optional[str]
    files_changed: Optional[int]
    additions: Optional[int]
    deletions: Optional[int]
    review_comments: Optional[int]
    merge_commit_sha: Optional[str]
    rejection_reason: Optional[str]
    approval_notes: Optional[str]


class ApproveRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=1000)


class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)


class ApproveResponse(BaseModel):
    message: str
    pr_id: UUID
    pr_number: Optional[int]
    github_pr_url: Optional[str]


class RejectResponse(BaseModel):
    message: str
    pr_id: UUID
    reason: str


class MergeRateDataPoint(BaseModel):
    date: str
    submitted: int
    merged: int
    merge_rate: float


class PRStats(BaseModel):
    total_prs: int
    merged: int
    open: int
    draft: int
    rejected: int
    closed: int
    overall_merge_rate: float
    avg_merge_probability: Optional[float]
    merge_rate_over_time: List[MergeRateDataPoint]


class PaginatedPRs(BaseModel):
    items: List[PRListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedPRs, summary="List all pull requests")
async def list_pull_requests(
    pr_status: Optional[str] = Query(None, alias="status"),
    repo_id: Optional[UUID] = Query(None),
    is_draft: Optional[bool] = Query(None),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaginatedPRs:
    stmt = select(PRModel)

    if pr_status:
        if pr_status not in VALID_PR_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status. Valid: {VALID_PR_STATUSES}")
        stmt = stmt.where(PRModel.pr_status == pr_status)
    if repo_id:
        stmt = stmt.where(PRModel.repo_id == repo_id)
    if is_draft is not None:
        stmt = stmt.where(PRModel.is_draft == is_draft)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total: int = count_result.scalar_one()

    stmt = stmt.order_by(PRModel.created_at.desc().nullslast())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    prs = result.scalars().all()

    total_pages = max(1, (total + pagination.page_size - 1) // pagination.page_size)
    return PaginatedPRs(
        items=[PRListItem.from_orm(p) for p in prs],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
    )


@router.get("/pending", response_model=List[PRListItem], summary="PRs awaiting approval")
async def get_pending_prs(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[PRListItem]:
    """Return all draft PRs that require human approval before submitting."""
    result = await db.execute(
        select(PRModel)
        .where(PRModel.pr_status == "draft")
        .order_by(PRModel.created_at.asc())
    )
    prs = result.scalars().all()
    return [PRListItem.from_orm(p) for p in prs]


@router.get("/stats", response_model=PRStats, summary="PR merge rate and stats")
async def get_pr_stats(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PRStats:
    """Return merge/acceptance rate charts and KPIs."""
    # Aggregate counts
    status_result = await db.execute(
        select(PRModel.pr_status, func.count(PRModel.id)).group_by(PRModel.pr_status)
    )
    counts = {row[0]: row[1] for row in status_result.all()}
    total = sum(counts.values())
    merged = counts.get("merged", 0)
    merge_rate = round((merged / total * 100), 2) if total > 0 else 0.0

    # Avg merge probability
    avg_result = await db.execute(select(func.avg(PRModel.merge_probability)))
    avg_prob = avg_result.scalar_one()

    # Daily merge rate over `days`
    since = datetime.utcnow() - timedelta(days=days)
    daily_result = await db.execute(
        select(
            func.date(PRModel.created_at).label("date"),
            func.count(PRModel.id).label("submitted"),
            func.sum(
                func.cast(PRModel.pr_status == "merged", func.Integer)
            ).label("merged_count"),
        )
        .where(PRModel.created_at >= since)
        .group_by(func.date(PRModel.created_at))
        .order_by(func.date(PRModel.created_at).asc())
    )
    merge_rate_over_time = []
    for row in daily_result.all():
        submitted = row[1] or 0
        day_merged = int(row[2] or 0)
        merge_rate_over_time.append(
            MergeRateDataPoint(
                date=str(row[0]),
                submitted=submitted,
                merged=day_merged,
                merge_rate=round(day_merged / submitted * 100, 2) if submitted > 0 else 0.0,
            )
        )

    return PRStats(
        total_prs=total,
        merged=merged,
        open=counts.get("open", 0),
        draft=counts.get("draft", 0),
        rejected=counts.get("rejected", 0),
        closed=counts.get("closed", 0),
        overall_merge_rate=merge_rate,
        avg_merge_probability=round(float(avg_prob), 2) if avg_prob else None,
        merge_rate_over_time=merge_rate_over_time,
    )


@router.get("/{pr_id}", response_model=PRDetail, summary="Get PR detail")
async def get_pull_request(
    pr_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PRDetail:
    result = await db.execute(select(PRModel).where(PRModel.id == pr_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pull request not found")
    return PRDetail.from_orm(pr)


@router.post(
    "/{pr_id}/approve",
    response_model=ApproveResponse,
    summary="Approve draft PR for submission",
)
async def approve_pull_request(
    pr_id: UUID,
    request: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    github: GitHubService = Depends(get_github_service),
    _key: str = Depends(verify_api_key),
) -> ApproveResponse:
    """Approve a draft PR — converts it from draft to ready-for-review on GitHub."""
    result = await db.execute(select(PRModel).where(PRModel.id == pr_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pull request not found")

    if pr.pr_status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"PR is already '{pr.pr_status}', not draft",
        )

    if not pr.pr_number or not pr.repo_full_name:
        raise HTTPException(status_code=422, detail="PR has no GitHub number or repo associated")

    # Convert from draft → ready on GitHub
    github_pr = await github.convert_pr_to_ready(pr.repo_full_name, pr.pr_number)

    pr.pr_status = "open"
    pr.is_draft = False
    pr.approval_notes = request.notes
    await db.flush()

    return ApproveResponse(
        message="PR approved and converted to ready-for-review on GitHub",
        pr_id=pr_id,
        pr_number=pr.pr_number,
        github_pr_url=github_pr.get("html_url") if isinstance(github_pr, dict) else pr.url,
    )


@router.post(
    "/{pr_id}/reject",
    response_model=RejectResponse,
    summary="Reject a draft PR",
)
async def reject_pull_request(
    pr_id: UUID,
    request: RejectRequest,
    db: AsyncSession = Depends(get_db),
    github: GitHubService = Depends(get_github_service),
    _key: str = Depends(verify_api_key),
) -> RejectResponse:
    """Reject a draft PR and close it on GitHub."""
    result = await db.execute(select(PRModel).where(PRModel.id == pr_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pull request not found")

    if pr.pr_status not in ("draft", "open"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot reject PR with status '{pr.pr_status}'",
        )

    # Close on GitHub if we have a real PR number
    if pr.pr_number and pr.repo_full_name:
        try:
            owner, repo_name = pr.repo_full_name.split("/", 1)
            github_repo = await github.get_repo(owner, repo_name)
            github_pr = github_repo.get_pull(pr.pr_number)
            github_pr.edit(state="closed")
            logger.info("Closed GitHub PR #%s for repo %s", pr.pr_number, pr.repo_full_name)
        except Exception as exc:
            logger.error("Failed to close GitHub PR: %s", exc)

    pr.pr_status = "rejected"
    pr.rejection_reason = request.reason
    await db.flush()

    return RejectResponse(
        message="PR rejected and closed",
        pr_id=pr_id,
        reason=request.reason,
    )
