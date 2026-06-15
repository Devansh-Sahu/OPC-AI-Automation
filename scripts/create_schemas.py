import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\devansh\OneDrive\Desktop\Open Source Engineer\backend")

schemas_init = """from .repository import RepositoryBase, RepositoryCreate, RepositoryUpdate, RepositoryInDB
from .issue import IssueBase, IssueCreate, IssueUpdate, IssueInDB
from .pull_request import PullRequestBase, PullRequestCreate, PullRequestUpdate, PullRequestInDB
from .agent_run import AgentRunBase, AgentRunCreate, AgentRunUpdate, AgentRunInDB
from .analytics import DashboardStats, CostStats, PerformanceStats

__all__ = [
    "RepositoryBase", "RepositoryCreate", "RepositoryUpdate", "RepositoryInDB",
    "IssueBase", "IssueCreate", "IssueUpdate", "IssueInDB",
    "PullRequestBase", "PullRequestCreate", "PullRequestUpdate", "PullRequestInDB",
    "AgentRunBase", "AgentRunCreate", "AgentRunUpdate", "AgentRunInDB",
    "DashboardStats", "CostStats", "PerformanceStats"
]
"""

repository_py = """from pydantic import BaseModel
from typing import Optional, Dict
from uuid import UUID
from datetime import datetime

class RepositoryBase(BaseModel):
    github_url: str
    name: str
    owner: str
    description: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    build_system: Optional[str] = None
    test_framework: Optional[str] = None
    stars: int = 0
    forks: int = 0
    open_issues_count: int = 0
    gsoc_history: bool = False
    foundation_type: Optional[str] = None
    maintainer_responsiveness_score: float = 0.0
    pr_acceptance_rate: float = 0.0
    stars_growth_rate: float = 0.0
    composite_quality_score: float = 0.0

class RepositoryCreate(RepositoryBase):
    pass

class RepositoryUpdate(BaseModel):
    description: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None
    build_system: Optional[str] = None
    test_framework: Optional[str] = None
    stars: Optional[int] = None
    forks: Optional[int] = None
    open_issues_count: Optional[int] = None
    maintainer_responsiveness_score: Optional[float] = None
    pr_acceptance_rate: Optional[float] = None
    stars_growth_rate: Optional[float] = None
    composite_quality_score: Optional[float] = None
    analysis_json: Optional[Dict] = None
    last_analyzed_at: Optional[datetime] = None
    last_discovered_at: Optional[datetime] = None
    is_active: Optional[bool] = None

class RepositoryInDB(RepositoryBase):
    id: UUID
    analysis_json: Optional[Dict] = None
    last_analyzed_at: Optional[datetime] = None
    last_discovered_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
"""

issue_py = """from pydantic import BaseModel
from typing import Optional, List, Dict
from uuid import UUID
from datetime import datetime

class IssueBase(BaseModel):
    repository_id: UUID
    github_issue_number: int
    title: str
    body: Optional[str] = None
    labels: Optional[List[str]] = None
    complexity_tier: Optional[str] = None
    difficulty_score: float = 0.0
    merge_probability_score: float = 0.0
    engagement_score: float = 0.0
    composite_score: float = 0.0
    status: str = "discovered"
    skip_reason: Optional[str] = None

class IssueCreate(IssueBase):
    pass

class IssueUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    labels: Optional[List[str]] = None
    complexity_tier: Optional[str] = None
    difficulty_score: Optional[float] = None
    merge_probability_score: Optional[float] = None
    engagement_score: Optional[float] = None
    composite_score: Optional[float] = None
    status: Optional[str] = None
    skip_reason: Optional[str] = None
    assigned_agent_run_id: Optional[UUID] = None

class IssueInDB(IssueBase):
    id: UUID
    assigned_agent_run_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
"""

pull_request_py = """from pydantic import BaseModel
from typing import Optional, Dict
from uuid import UUID
from datetime import datetime

class PullRequestBase(BaseModel):
    repository_id: UUID
    issue_id: UUID
    branch_name: str
    title: str
    body: Optional[str] = None
    status: str = "draft"

class PullRequestCreate(PullRequestBase):
    pass

class PullRequestUpdate(BaseModel):
    github_pr_number: Optional[int] = None
    github_pr_url: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    user_approved_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    test_results_json: Optional[Dict] = None
    review_comments_json: Optional[Dict] = None
    diff_patch: Optional[str] = None

class PullRequestInDB(PullRequestBase):
    id: UUID
    github_pr_number: Optional[int] = None
    github_pr_url: Optional[str] = None
    user_approved_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    test_results_json: Optional[Dict] = None
    review_comments_json: Optional[Dict] = None
    diff_patch: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
"""

agent_run_py = """from pydantic import BaseModel
from typing import Optional, Dict
from uuid import UUID
from datetime import datetime

class AgentRunBase(BaseModel):
    issue_id: UUID
    workflow_run_id: str
    current_step: str
    total_steps: int = 0
    status: str = "pending"
    cost_tokens: int = 0
    cost_usd: float = 0.0

class AgentRunCreate(AgentRunBase):
    pass

class AgentRunUpdate(BaseModel):
    current_step: Optional[str] = None
    total_steps: Optional[int] = None
    status: Optional[str] = None
    checkpoint_state_json: Optional[Dict] = None
    cost_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class AgentRunInDB(AgentRunBase):
    id: UUID
    checkpoint_state_json: Optional[Dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True
"""

analytics_py = """from pydantic import BaseModel
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
"""

def write_file(path, content):
    with open(BASE_DIR / path, 'w', encoding='utf-8') as f:
        f.write(content)

write_file('schemas/__init__.py', schemas_init)
write_file('schemas/repository.py', repository_py)
write_file('schemas/issue.py', issue_py)
write_file('schemas/pull_request.py', pull_request_py)
write_file('schemas/agent_run.py', agent_run_py)
write_file('schemas/analytics.py', analytics_py)
