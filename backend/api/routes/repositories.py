# backend/api/routes/repositories.py
"""
Repository CRUD & analysis routes.

Endpoints:
  GET    /repositories                   — paginated list with filters
  GET    /repositories/{id}              — full repo detail
  GET    /repositories/{id}/issues       — issues for a repo
  GET    /repositories/{id}/knowledge    — repo knowledge/analysis
  POST   /repositories/{id}/reanalyze   — trigger re-analysis
  DELETE /repositories/{id}             — soft-delete (mark inactive)
"""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_pagination, PaginationParams, verify_api_key
from backend.models.repository import Repository as RepoModel
from backend.models.issue import Issue as IssueModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas (response models)
# ---------------------------------------------------------------------------

class RepositoryBase(BaseModel):
    id: UUID
    owner: str
    name: str
    full_name: str
    description: Optional[str]
    language: Optional[str]
    stars: int
    forks: int
    open_issues_count: int
    quality_score: float
    composite_score: Optional[float]
    is_active: bool
    foundation: Optional[str]
    topics: Optional[List[str]]
    last_analyzed_at: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class RepositoryDetail(RepositoryBase):
    readme_summary: Optional[str]
    architecture_notes: Optional[str]
    primary_language: Optional[str]
    languages: Optional[dict]
    contributor_count: Optional[int]
    last_commit_at: Optional[str]
    license: Optional[str]
    homepage: Optional[str]
    has_ci: Optional[bool]
    has_tests: Optional[bool]
    test_coverage_pct: Optional[float]
    code_health_score: Optional[float]


class IssueListItem(BaseModel):
    id: UUID
    number: int
    title: str
    complexity_tier: Optional[str]
    composite_score: Optional[float]
    status: str
    created_at: str

    class Config:
        from_attributes = True


class RepoKnowledge(BaseModel):
    repo_id: UUID
    full_name: str
    readme_summary: Optional[str]
    architecture_notes: Optional[str]
    file_tree_summary: Optional[str]
    key_files: Optional[List[str]]
    test_framework: Optional[str]
    build_system: Optional[str]
    contributing_guide: Optional[str]
    code_style: Optional[str]


class PaginatedRepositories(BaseModel):
    items: List[RepositoryBase]
    total: int
    page: int
    page_size: int
    total_pages: int


class ReanalyzeResponse(BaseModel):
    message: str
    repo_id: UUID
    task_id: Optional[str]


class DeleteResponse(BaseModel):
    message: str
    repo_id: UUID


# ---------------------------------------------------------------------------
# Background task helper
# ---------------------------------------------------------------------------

async def _trigger_reanalysis(repo_id: str) -> None:
    """Background task: enqueue re-analysis job via Redis or direct call."""
    try:
        from backend.core.task_queue import enqueue_task
        await enqueue_task("analyze_repo", {"repo_id": repo_id})
        logger.info("Re-analysis enqueued for repo %s", repo_id)
    except Exception as exc:
        logger.error("Failed to enqueue re-analysis for repo %s: %s", repo_id, exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedRepositories, summary="List all discovered repositories")
async def list_repositories(
    language: Optional[str] = Query(None, description="Filter by primary language"),
    foundation: Optional[str] = Query(None, description="Filter by foundation (cncf, apache, gsoc, ...)"),
    min_score: Optional[float] = Query(None, ge=0, le=100, description="Minimum composite score"),
    search: Optional[str] = Query(None, description="Full-text search on name/description"),
    is_active: bool = Query(True, description="Only return active repos"),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaginatedRepositories:
    """Return a paginated list of repositories with optional filters."""
    stmt = select(RepoModel)

    if is_active:
        stmt = stmt.where(RepoModel.is_active == True)  # noqa: E712
    if language:
        stmt = stmt.where(RepoModel.language.ilike(f"%{language}%"))
    if foundation:
        stmt = stmt.where(RepoModel.foundation.ilike(f"%{foundation}%"))
    if min_score is not None:
        stmt = stmt.where(RepoModel.composite_score >= min_score)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            (RepoModel.name.ilike(pattern)) | (RepoModel.description.ilike(pattern))
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    stmt = stmt.order_by(RepoModel.composite_score.desc().nullslast())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    repos = result.scalars().all()

    total_pages = max(1, (total + pagination.page_size - 1) // pagination.page_size)
    return PaginatedRepositories(
        items=[RepositoryBase.from_orm(r) for r in repos],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
    )


@router.get("/{repo_id}", response_model=RepositoryDetail, summary="Get repository detail")
async def get_repository(
    repo_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> RepositoryDetail:
    """Return full detail for a single repository."""
    result = await db.execute(select(RepoModel).where(RepoModel.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return RepositoryDetail.from_orm(repo)


@router.get("/{repo_id}/issues", response_model=List[IssueListItem], summary="Issues for a repo")
async def list_repo_issues(
    repo_id: UUID,
    complexity_tier: Optional[str] = Query(None),
    issue_status: Optional[str] = Query(None, alias="status"),
    min_score: Optional[float] = Query(None, ge=0),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[IssueListItem]:
    """Return issues belonging to a repository."""
    # Verify repo exists
    repo_result = await db.execute(select(RepoModel).where(RepoModel.id == repo_id))
    if not repo_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    stmt = select(IssueModel).where(IssueModel.repo_id == repo_id)
    if complexity_tier:
        stmt = stmt.where(IssueModel.complexity_tier == complexity_tier.upper())
    if issue_status:
        stmt = stmt.where(IssueModel.status == issue_status)
    if min_score is not None:
        stmt = stmt.where(IssueModel.composite_score >= min_score)
    stmt = stmt.order_by(IssueModel.composite_score.desc().nullslast())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)

    result = await db.execute(stmt)
    issues = result.scalars().all()
    return [IssueListItem.from_orm(i) for i in issues]


@router.get("/{repo_id}/knowledge", response_model=RepoKnowledge, summary="Get repo knowledge/analysis")
async def get_repo_knowledge(
    repo_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> RepoKnowledge:
    """Return the AI-generated knowledge base for a repository."""
    result = await db.execute(select(RepoModel).where(RepoModel.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    return RepoKnowledge(
        repo_id=repo.id,
        full_name=repo.full_name,
        readme_summary=getattr(repo, "readme_summary", None),
        architecture_notes=getattr(repo, "architecture_notes", None),
        file_tree_summary=getattr(repo, "file_tree_summary", None),
        key_files=getattr(repo, "key_files", None),
        test_framework=getattr(repo, "test_framework", None),
        build_system=getattr(repo, "build_system", None),
        contributing_guide=getattr(repo, "contributing_guide", None),
        code_style=getattr(repo, "code_style", None),
    )


@router.post(
    "/{repo_id}/reanalyze",
    response_model=ReanalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger re-analysis of a repository",
)
async def reanalyze_repository(
    repo_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ReanalyzeResponse:
    """Enqueue a background job to re-analyze this repository."""
    result = await db.execute(select(RepoModel).where(RepoModel.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    background_tasks.add_task(_trigger_reanalysis, str(repo_id))
    return ReanalyzeResponse(
        message="Re-analysis triggered",
        repo_id=repo_id,
        task_id=None,
    )


@router.delete(
    "/{repo_id}",
    response_model=DeleteResponse,
    summary="Soft-delete a repository (mark inactive)",
)
async def delete_repository(
    repo_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> DeleteResponse:
    """Mark a repository as inactive (soft delete)."""
    result = await db.execute(select(RepoModel).where(RepoModel.id == repo_id))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    await db.execute(
        update(RepoModel).where(RepoModel.id == repo_id).values(is_active=False)
    )
    return DeleteResponse(message="Repository marked as inactive", repo_id=repo_id)
