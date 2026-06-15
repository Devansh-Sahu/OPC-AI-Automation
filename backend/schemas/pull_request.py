from pydantic import BaseModel
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
