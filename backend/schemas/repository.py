from pydantic import BaseModel
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
