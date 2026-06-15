import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, Float, Integer, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    github_url: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    owner: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    framework: Mapped[str | None] = mapped_column(String, nullable=True)
    build_system: Mapped[str | None] = mapped_column(String, nullable=True)
    test_framework: Mapped[str | None] = mapped_column(String, nullable=True)
    
    stars: Mapped[int] = mapped_column(Integer, default=0)
    forks: Mapped[int] = mapped_column(Integer, default=0)
    open_issues_count: Mapped[int] = mapped_column(Integer, default=0)
    
    gsoc_history: Mapped[bool] = mapped_column(Boolean, default=False)
    foundation_type: Mapped[str | None] = mapped_column(String, nullable=True)
    maintainer_responsiveness_score: Mapped[float] = mapped_column(Float, default=0.0)
    pr_acceptance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    stars_growth_rate: Mapped[float] = mapped_column(Float, default=0.0)
    composite_quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    analysis_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    last_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    issues = relationship("Issue", back_populates="repository")
    pull_requests = relationship("PullRequest", back_populates="repository")
