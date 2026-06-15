# backend/api/routes/agent_runs.py
"""
Agent run management routes.

Endpoints:
  GET  /agent-runs           — paginated list with filters
  GET  /agent-runs/active    — currently running agents
  GET  /agent-runs/{id}      — run detail with all steps
  GET  /agent-runs/{id}/logs — execution logs for a run
  POST /agent-runs/{id}/cancel  — cancel running workflow
  POST /agent-runs/{id}/resume  — resume from checkpoint
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_pagination, PaginationParams, verify_api_key
from backend.models.agent_run import AgentRun as AgentRunModel
from backend.models.agent_run_step import AgentRunStep as StepModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AgentRunStep(BaseModel):
    id: UUID
    step_name: str
    step_type: str
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    input_summary: Optional[str]
    output_summary: Optional[str]
    error_message: Optional[str]
    tokens_used: Optional[int]
    model_used: Optional[str]

    class Config:
        from_attributes = True


class AgentRunListItem(BaseModel):
    id: UUID
    issue_id: Optional[UUID]
    repo_id: Optional[UUID]
    repo_full_name: Optional[str]
    issue_number: Optional[int]
    issue_title: Optional[str]
    status: str
    current_step: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    total_tokens: Optional[int]
    estimated_cost_usd: Optional[float]
    pr_url: Optional[str]
    pr_number: Optional[int]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class AgentRunDetail(AgentRunListItem):
    steps: List[AgentRunStep] = []
    plan: Optional[Dict[str, Any]]
    checkpoint_data: Optional[Dict[str, Any]]
    llm_model: Optional[str]
    agent_version: Optional[str]


class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    step: Optional[str]
    message: str
    metadata: Optional[Dict[str, Any]]


class AgentRunLogs(BaseModel):
    run_id: UUID
    entries: List[LogEntry]
    total_entries: int


class CancelResponse(BaseModel):
    message: str
    run_id: UUID
    cancelled_at: datetime


class ResumeResponse(BaseModel):
    message: str
    run_id: UUID
    resumed_from_step: Optional[str]


class PaginatedAgentRuns(BaseModel):
    items: List[AgentRunListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=PaginatedAgentRuns, summary="List all agent runs")
async def list_agent_runs(
    run_status: Optional[str] = Query(None, alias="status", description="pending|running|completed|failed|cancelled"),
    repo_id: Optional[UUID] = Query(None),
    issue_id: Optional[UUID] = Query(None),
    pagination: PaginationParams = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> PaginatedAgentRuns:
    stmt = select(AgentRunModel)

    if run_status:
        stmt = stmt.where(AgentRunModel.status == run_status)
    if repo_id:
        stmt = stmt.where(AgentRunModel.repo_id == repo_id)
    if issue_id:
        stmt = stmt.where(AgentRunModel.issue_id == issue_id)

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total: int = count_result.scalar_one()

    stmt = stmt.order_by(AgentRunModel.started_at.desc().nullslast())
    stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await db.execute(stmt)
    runs = result.scalars().all()

    total_pages = max(1, (total + pagination.page_size - 1) // pagination.page_size)
    return PaginatedAgentRuns(
        items=[AgentRunListItem.from_orm(r) for r in runs],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=total_pages,
    )


@router.get("/active", response_model=List[AgentRunListItem], summary="Currently running agents")
async def get_active_runs(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[AgentRunListItem]:
    """Return all currently running agent workflows."""
    result = await db.execute(
        select(AgentRunModel).where(AgentRunModel.status == "running").order_by(AgentRunModel.started_at.desc())
    )
    runs = result.scalars().all()
    return [AgentRunListItem.from_orm(r) for r in runs]


@router.get("/{run_id}", response_model=AgentRunDetail, summary="Get agent run detail")
async def get_agent_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> AgentRunDetail:
    result = await db.execute(select(AgentRunModel).where(AgentRunModel.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")

    # Fetch steps
    steps_result = await db.execute(
        select(StepModel)
        .where(StepModel.agent_run_id == run_id)
        .order_by(StepModel.started_at.asc())
    )
    steps = steps_result.scalars().all()

    detail = AgentRunDetail.from_orm(run)
    detail.steps = [AgentRunStep.from_orm(s) for s in steps]
    return detail


@router.get("/{run_id}/logs", response_model=AgentRunLogs, summary="Get execution logs for a run")
async def get_run_logs(
    run_id: UUID,
    level: Optional[str] = Query(None, description="Filter by log level: DEBUG|INFO|WARNING|ERROR"),
    limit: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> AgentRunLogs:
    """Return execution log entries for an agent run."""
    result = await db.execute(select(AgentRunModel).where(AgentRunModel.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")

    # Fetch from logs table or reconstruct from steps
    try:
        from backend.models.agent_run_log import AgentRunLog as LogModel
        stmt = select(LogModel).where(LogModel.agent_run_id == run_id)
        if level:
            stmt = stmt.where(LogModel.level == level.upper())
        stmt = stmt.order_by(LogModel.timestamp.asc()).limit(limit)
        logs_result = await db.execute(stmt)
        logs = logs_result.scalars().all()
        entries = [
            LogEntry(
                timestamp=log.timestamp,
                level=log.level,
                step=log.step,
                message=log.message,
                metadata=log.metadata,
            )
            for log in logs
        ]
    except Exception:
        # Fallback: synthesize from steps
        steps_result = await db.execute(
            select(StepModel).where(StepModel.agent_run_id == run_id).order_by(StepModel.started_at)
        )
        steps = steps_result.scalars().all()
        entries = []
        for s in steps:
            if s.started_at:
                entries.append(LogEntry(
                    timestamp=s.started_at,
                    level="INFO",
                    step=s.step_name,
                    message=f"Step '{s.step_name}' started",
                    metadata=None,
                ))
            if s.completed_at:
                entries.append(LogEntry(
                    timestamp=s.completed_at,
                    level="ERROR" if s.status == "failed" else "INFO",
                    step=s.step_name,
                    message=s.error_message or f"Step '{s.step_name}' completed with status '{s.status}'",
                    metadata=None,
                ))

    return AgentRunLogs(run_id=run_id, entries=entries[:limit], total_entries=len(entries))


@router.post(
    "/{run_id}/cancel",
    response_model=CancelResponse,
    summary="Cancel a running agent workflow",
)
async def cancel_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> CancelResponse:
    result = await db.execute(select(AgentRunModel).where(AgentRunModel.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")

    if run.status not in ("running", "pending"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot cancel run with status '{run.status}'",
        )

    run.status = "cancelled"
    cancelled_at = datetime.utcnow()
    run.completed_at = cancelled_at
    await db.flush()

    # Signal the running task to stop via Redis or event
    try:
        from backend.core.redis_client import get_redis
        redis = await get_redis()
        await redis.publish(f"cancel:{run_id}", "1")
    except Exception as exc:
        logger.warning("Could not publish cancel signal for run %s: %s", run_id, exc)

    return CancelResponse(message="Run cancellation requested", run_id=run_id, cancelled_at=cancelled_at)


@router.post(
    "/{run_id}/resume",
    response_model=ResumeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resume an agent run from checkpoint",
)
async def resume_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ResumeResponse:
    result = await db.execute(select(AgentRunModel).where(AgentRunModel.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")

    if run.status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Can only resume failed or cancelled runs, not '{run.status}'",
        )

    checkpoint = run.checkpoint_data or {}
    last_step = checkpoint.get("last_completed_step")

    # Re-enqueue the workflow from checkpoint
    try:
        from backend.core.task_queue import enqueue_task
        await enqueue_task(
            "run_issue_workflow",
            {
                "issue_id": str(run.issue_id),
                "resume_run_id": str(run_id),
                "resume_from_step": last_step,
            },
        )
    except Exception as exc:
        logger.error("Failed to enqueue resume for run %s: %s", run_id, exc)
        raise HTTPException(status_code=500, detail="Failed to enqueue resume task")

    run.status = "running"
    await db.flush()

    return ResumeResponse(
        message="Run resumed from checkpoint",
        run_id=run_id,
        resumed_from_step=last_step,
    )
