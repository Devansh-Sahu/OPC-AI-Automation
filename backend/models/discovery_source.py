from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.sql import func
from backend.core.database import Base

class DiscoverySource(Base):
    __tablename__ = "discovery_sources"

    name = Column(String, primary_key=True, index=True)
    is_enabled = Column(Boolean, default=True)
    repos_found = Column(Integer, default=0)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
