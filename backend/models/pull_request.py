import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class PullRequest(Base):
    __tablename__ = "pull_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repositories.id"))
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id"))
    
    github_pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    github_pr_url: Mapped[str | None] = mapped_column(String, nullable=True)
    branch_name: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(String, nullable=True)
    
    status: Mapped[str] = mapped_column(String, default="draft") # draft, submitted, merged, rejected, changes_requested
    
    user_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    test_results_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    review_comments_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diff_patch: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    repository = relationship("Repository", back_populates="pull_requests")
    issue = relationship("Issue", back_populates="pull_requests")
