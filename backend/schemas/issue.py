from pydantic import BaseModel
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
