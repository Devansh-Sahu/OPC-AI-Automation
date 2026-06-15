import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pull_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pull_requests.id"))
    
    outcome: Mapped[str] = mapped_column(String) # merged, rejected, changes_requested, abandoned
    maintainer_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    lessons_learned_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    xgboost_features_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
