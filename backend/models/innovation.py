import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from backend.core.database import Base

class InnovationProposal(Base):
    __tablename__ = "innovation_proposals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    repo_id = Column(UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), index=True, nullable=True)
    title = Column(String, index=True)
    description = Column(Text)
    status = Column(String, default="proposed")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    impact_score = Column(Float, nullable=True)
    effort_score = Column(Float, nullable=True)
