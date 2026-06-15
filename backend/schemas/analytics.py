from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime

class DashboardStats(BaseModel):
    total_issues_found: int
    draft_prs_created: int
    prs_merged: int
    success_rate_percent: float
    active_agent_runs: int
    total_cost_usd: float

class CostStats(BaseModel):
    total_tokens_used: int
    estimated_usd_cost: float
    per_model_breakdown: Dict[str, int] # model -> tokens

class PerformanceStats(BaseModel):
    per_agent_success_rate: Dict[str, float]
    avg_duration_minutes: float
    total_runs: int
