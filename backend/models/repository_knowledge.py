import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class RepositoryKnowledge(Base):
    __tablename__ = "repository_knowledge"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repositories.id"))
    
    knowledge_type: Mapped[str] = mapped_column(String) # ast, dependency_graph, readme, architecture, test_patterns, contribution_patterns
    content_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedding_collection_name: Mapped[str | None] = mapped_column(String, nullable=True)
    
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    function_count: Mapped[int] = mapped_column(Integer, default=0)
    class_count: Mapped[int] = mapped_column(Integer, default=0)
    architecture_pattern: Mapped[str | None] = mapped_column(String, nullable=True)
    
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
