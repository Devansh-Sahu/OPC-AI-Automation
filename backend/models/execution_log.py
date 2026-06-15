import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_runs.id"))
    
    agent_name: Mapped[str] = mapped_column(String)
    step_name: Mapped[str] = mapped_column(String)
    
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    
    status: Mapped[str] = mapped_column(String, default="success") # success, failed, skipped
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    agent_run = relationship("AgentRun", back_populates="execution_logs")
