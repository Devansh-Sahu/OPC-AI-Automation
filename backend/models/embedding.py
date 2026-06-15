import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, JSON, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repositories.id"))
    
    chunk_id: Mapped[str] = mapped_column(String) # ChromaDB doc id
    file_path: Mapped[str] = mapped_column(String)
    chunk_type: Mapped[str] = mapped_column(String) # function, class, module, method
    chunk_text_hash: Mapped[str] = mapped_column(String)
    
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    chroma_collection: Mapped[str] = mapped_column(String)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
