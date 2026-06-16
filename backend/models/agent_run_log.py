import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from backend.core.database import Base

class AgentRunLog(Base):
    __tablename__ = "agent_run_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    agent_run_id = Column(UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    level = Column(String, default="INFO")
    step = Column(String, nullable=True)
    message = Column(Text)
    metadata_payload = Column("metadata", JSONB, nullable=True)
