import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repositories.id"))
    github_issue_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(String, nullable=True)
    labels: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    complexity_tier: Mapped[str | None] = mapped_column(String, nullable=True) # SENIOR, STAFF, INNOVATION
    difficulty_score: Mapped[float] = mapped_column(Float, default=0.0) # 1-10
    merge_probability_score: Mapped[float] = mapped_column(Float, default=0.0) # 0-100
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    status: Mapped[str] = mapped_column(String, default="discovered") # discovered, analyzing, in_progress, pr_created, completed, skipped
    skip_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    repository = relationship("Repository", back_populates="issues")
    pull_requests = relationship("PullRequest", back_populates="issue")
    agent_runs = relationship("AgentRun", back_populates="issue")
