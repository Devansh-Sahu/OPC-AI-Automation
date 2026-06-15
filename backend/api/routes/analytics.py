# backend/api/routes/analytics.py
"""
Analytics and KPI routes.

Endpoints:
  GET /analytics/dashboard         — overall KPIs
  GET /analytics/merge-rate        — merge rate over time
  GET /analytics/agent-performance — per-agent metrics
  GET /analytics/cost              — token usage and USD cost
  GET /analytics/top-repos         — top contributing repos
  GET /analytics/contribution-streak — streak, totals
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db, get_cost_tracker, verify_api_key, CostTracker
from backend.models.agent_run import AgentRun as AgentRunModel
from backend.models.pull_request import PullRequest as PRModel
from backend.models.issue import Issue as IssueModel
from backend.models.repository import Repository as RepoModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class DashboardKPIs(BaseModel):
    total_issues_scored: int
    total_issues_solved: int
    total_prs_created: int
    total_prs_merged: int
    success_rate: float
    active_runs: int
    total_repos: int
    total_tokens_used: int
    estimated_cost_usd: float
    issues_in_progress: int


class MergeRatePoint(BaseModel):
    period: str
    submitted: int
    merged: int
    merge_rate_pct: float


class MergeRateResponse(BaseModel):
    granularity: str
    data: List[MergeRatePoint]


class AgentPerformanceItem(BaseModel):
    agent_step: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    avg_duration_seconds: Optional[float]
    avg_tokens_used: Optional[float]
    estimated_cost_usd: float


class CostBreakdown(BaseModel):
    model: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    run_count: int


class CostAnalytics(BaseModel):
    total_tokens: int
    total_estimated_cost_usd: float
    by_model: List[CostBreakdown]
    by_day: List[Dict]


class TopRepo(BaseModel):
    repo_id: UUID
    full_name: str
    prs_created: int
    prs_merged: int
    issues_solved: int
    merge_rate: float


class ContributionStreak(BaseModel):
    current_streak_days: int
    longest_streak_days: int
    total_prs_merged: int
    repositories_contributed_to: int
    first_contribution_date: Optional[datetime]
    last_contribution_date: Optional[datetime]
    daily_activity: List[Dict]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardKPIs, summary="Dashboard KPIs")
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    cost_tracker: CostTracker = Depends(get_cost_tracker),
    _key: str = Depends(verify_api_key),
) -> DashboardKPIs:
    """Return all top-level KPIs for the main dashboard."""
    # Issues
    total_issues = (await db.execute(select(func.count()).select_from(IssueModel))).scalar_one()
    solved_issues = (
        await db.execute(
            select(func.count()).select_from(IssueModel).where(IssueModel.status.in_(["merged", "pr_created"]))
        )
    ).scalar_one()
    in_progress = (
        await db.execute(
            select(func.count()).select_from(IssueModel).where(IssueModel.status == "in_progress")
        )
    ).scalar_one()

    # PRs
    total_prs = (await db.execute(select(func.count()).select_from(PRModel))).scalar_one()
    merged_prs = (
        await db.execute(
            select(func.count()).select_from(PRModel).where(PRModel.pr_status == "merged")
        )
    ).scalar_one()

    # Active runs
    active_runs = (
        await db.execute(
            select(func.count()).select_from(AgentRunModel).where(AgentRunModel.status == "running")
        )
    ).scalar_one()

    # Repos
    total_repos = (await db.execute(select(func.count()).select_from(RepoModel))).scalar_one()

    # Cost
    cost_data = cost_tracker.get_total_cost()
    total_tokens = cost_data.get("total_tokens", 0)
    total_cost = cost_data.get("total_usd", 0.0)

    success_rate = round((merged_prs / total_prs * 100), 2) if total_prs > 0 else 0.0

    return DashboardKPIs(
        total_issues_scored=total_issues,
        total_issues_solved=solved_issues,
        total_prs_created=total_prs,
        total_prs_merged=merged_prs,
        success_rate=success_rate,
        active_runs=active_runs,
        total_repos=total_repos,
        total_tokens_used=total_tokens,
        estimated_cost_usd=total_cost,
        issues_in_progress=in_progress,
    )


@router.get("/merge-rate", response_model=MergeRateResponse, summary="Merge rate over time")
async def get_merge_rate(
    granularity: str = Query("daily", description="daily|weekly|monthly"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> MergeRateResponse:
    """Return PR merge rate aggregated by day/week/month."""
    since = datetime.utcnow() - timedelta(days=days)

    if granularity == "monthly":
        period_expr = func.strftime("%Y-%m", PRModel.created_at)
    elif granularity == "weekly":
        period_expr = func.strftime("%Y-W%W", PRModel.created_at)
    else:
        period_expr = func.date(PRModel.created_at)

    result = await db.execute(
        select(
            period_expr.label("period"),
            func.count(PRModel.id).label("submitted"),
            func.sum(
                func.cast(PRModel.pr_status == "merged", func.Integer)
            ).label("merged"),
        )
        .where(PRModel.created_at >= since)
        .group_by(period_expr)
        .order_by(period_expr.asc())
    )

    data = []
    for row in result.all():
        submitted = row[1] or 0
        merged = int(row[2] or 0)
        data.append(
            MergeRatePoint(
                period=str(row[0]),
                submitted=submitted,
                merged=merged,
                merge_rate_pct=round(merged / submitted * 100, 2) if submitted > 0 else 0.0,
            )
        )
    return MergeRateResponse(granularity=granularity, data=data)


@router.get("/agent-performance", response_model=List[AgentPerformanceItem], summary="Per-agent step performance")
async def get_agent_performance(
    db: AsyncSession = Depends(get_db),
    cost_tracker: CostTracker = Depends(get_cost_tracker),
    _key: str = Depends(verify_api_key),
) -> List[AgentPerformanceItem]:
    """Return success rates and costs per agent step."""
    from backend.models.agent_run_step import AgentRunStep as StepModel

    result = await db.execute(
        select(
            StepModel.step_name,
            func.count(StepModel.id).label("total"),
            func.sum(func.cast(StepModel.status == "completed", func.Integer)).label("successful"),
            func.sum(func.cast(StepModel.status == "failed", func.Integer)).label("failed"),
            func.avg(StepModel.duration_seconds).label("avg_duration"),
            func.avg(StepModel.tokens_used).label("avg_tokens"),
        )
        .group_by(StepModel.step_name)
        .order_by(func.count(StepModel.id).desc())
    )

    agent_costs = cost_tracker.get_cost_by_agent()
    items = []
    for row in result.all():
        step_name = row[0]
        total = row[1] or 0
        successful = int(row[2] or 0)
        failed = int(row[3] or 0)
        avg_dur = float(row[4]) if row[4] else None
        avg_tok = float(row[5]) if row[5] else None
        cost = agent_costs.get(step_name, {}).get("usd", 0.0)
        items.append(
            AgentPerformanceItem(
                agent_step=step_name,
                total_runs=total,
                successful_runs=successful,
                failed_runs=failed,
                success_rate=round(successful / total * 100, 2) if total > 0 else 0.0,
                avg_duration_seconds=round(avg_dur, 2) if avg_dur else None,
                avg_tokens_used=round(avg_tok, 0) if avg_tok else None,
                estimated_cost_usd=cost,
            )
        )
    return items


@router.get("/cost", response_model=CostAnalytics, summary="Token usage and USD cost breakdown")
async def get_cost_analytics(
    cost_tracker: CostTracker = Depends(get_cost_tracker),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> CostAnalytics:
    """Return token usage broken down by model."""
    total_data = cost_tracker.get_total_cost()
    model_data = cost_tracker.get_cost_by_model()

    by_model = [
        CostBreakdown(
            model=m,
            total_tokens=d.get("total_tokens", 0),
            prompt_tokens=d.get("prompt_tokens", 0),
            completion_tokens=d.get("completion_tokens", 0),
            estimated_cost_usd=d.get("usd", 0.0),
            run_count=d.get("run_count", 0),
        )
        for m, d in model_data.items()
    ]

    # Daily cost from runs table
    result = await db.execute(
        select(
            func.date(AgentRunModel.started_at).label("date"),
            func.sum(AgentRunModel.total_tokens).label("tokens"),
            func.sum(AgentRunModel.estimated_cost_usd).label("cost"),
        )
        .where(AgentRunModel.started_at >= datetime.utcnow() - timedelta(days=30))
        .group_by(func.date(AgentRunModel.started_at))
        .order_by(func.date(AgentRunModel.started_at).asc())
    )
    by_day = [
        {"date": str(row[0]), "tokens": int(row[1] or 0), "cost_usd": round(float(row[2] or 0), 6)}
        for row in result.all()
    ]

    return CostAnalytics(
        total_tokens=total_data.get("total_tokens", 0),
        total_estimated_cost_usd=total_data.get("total_usd", 0.0),
        by_model=by_model,
        by_day=by_day,
    )


@router.get("/top-repos", response_model=List[TopRepo], summary="Repositories with most contributions")
async def get_top_repos(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> List[TopRepo]:
    """Return top repos by number of PRs created/merged."""
    result = await db.execute(
        select(
            PRModel.repo_id,
            RepoModel.full_name,
            func.count(PRModel.id).label("prs_created"),
            func.sum(func.cast(PRModel.pr_status == "merged", func.Integer)).label("prs_merged"),
        )
        .join(RepoModel, PRModel.repo_id == RepoModel.id, isouter=True)
        .group_by(PRModel.repo_id, RepoModel.full_name)
        .order_by(func.count(PRModel.id).desc())
        .limit(limit)
    )
    items = []
    for row in result.all():
        prs_created = row[2] or 0
        prs_merged = int(row[3] or 0)
        items.append(
            TopRepo(
                repo_id=row[0],
                full_name=row[1] or "Unknown",
                prs_created=prs_created,
                prs_merged=prs_merged,
                issues_solved=prs_merged,
                merge_rate=round(prs_merged / prs_created * 100, 2) if prs_created > 0 else 0.0,
            )
        )
    return items


@router.get("/contribution-streak", response_model=ContributionStreak, summary="Daily contribution streak")
async def get_contribution_streak(
    db: AsyncSession = Depends(get_db),
    _key: str = Depends(verify_api_key),
) -> ContributionStreak:
    """Return streak data, total merged PRs, and daily activity for the last 90 days."""
    since = datetime.utcnow() - timedelta(days=90)

    # All merged PRs sorted by date
    result = await db.execute(
        select(func.date(PRModel.merged_at).label("day"))
        .where(and_(PRModel.pr_status == "merged", PRModel.merged_at >= since))
        .group_by(func.date(PRModel.merged_at))
        .order_by(func.date(PRModel.merged_at).asc())
    )
    merge_days = [row[0] for row in result.all() if row[0]]

    # Compute streaks
    current_streak = 0
    longest_streak = 0
    today = datetime.utcnow().date()

    if merge_days:
        # Current streak: walk backward from today
        check = today
        for _ in range(365):
            if str(check) in [str(d) for d in merge_days]:
                current_streak += 1
                check = check - timedelta(days=1)
            else:
                break

        # Longest streak
        streak = 1
        for i in range(1, len(merge_days)):
            from datetime import date
            prev = merge_days[i - 1] if isinstance(merge_days[i - 1], date) else datetime.strptime(str(merge_days[i - 1]), "%Y-%m-%d").date()
            curr = merge_days[i] if isinstance(merge_days[i], date) else datetime.strptime(str(merge_days[i]), "%Y-%m-%d").date()
            if (curr - prev).days == 1:
                streak += 1
                longest_streak = max(longest_streak, streak)
            else:
                streak = 1
        longest_streak = max(longest_streak, len(merge_days) and 1)

    # Total merged PRs
    total_merged = (
        await db.execute(
            select(func.count()).select_from(PRModel).where(PRModel.pr_status == "merged")
        )
    ).scalar_one()

    # Repos contributed to
    repos_contributed = (
        await db.execute(
            select(func.count(func.distinct(PRModel.repo_id))).where(PRModel.pr_status == "merged")
        )
    ).scalar_one()

    # First and last
    first_result = await db.execute(
        select(func.min(PRModel.merged_at)).where(PRModel.pr_status == "merged")
    )
    last_result = await db.execute(
        select(func.max(PRModel.merged_at)).where(PRModel.pr_status == "merged")
    )

    # Daily activity for heatmap
    daily_result = await db.execute(
        select(
            func.date(PRModel.merged_at).label("day"),
            func.count(PRModel.id).label("count"),
        )
        .where(and_(PRModel.pr_status == "merged", PRModel.merged_at >= since))
        .group_by(func.date(PRModel.merged_at))
        .order_by(func.date(PRModel.merged_at).asc())
    )
    daily_activity = [{"date": str(row[0]), "count": row[1]} for row in daily_result.all()]

    return ContributionStreak(
        current_streak_days=current_streak,
        longest_streak_days=longest_streak,
        total_prs_merged=total_merged,
        repositories_contributed_to=repos_contributed,
        first_contribution_date=first_result.scalar_one(),
        last_contribution_date=last_result.scalar_one(),
        daily_activity=daily_activity,
    )
