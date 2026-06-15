import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("issues.id"))
    
    workflow_run_id: Mapped[str] = mapped_column(String) # LangGraph thread_id
    current_step: Mapped[str] = mapped_column(String)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    
    status: Mapped[str] = mapped_column(String, default="pending") # pending, running, paused_for_approval, completed, failed, cancelled
    checkpoint_state_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    cost_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    issue = relationship("Issue", back_populates="agent_runs")
    execution_logs = relationship("ExecutionLog", back_populates="agent_run")
