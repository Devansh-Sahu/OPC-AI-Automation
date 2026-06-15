import os
from pathlib import Path

BASE_DIR = Path(r"C:\Users\devansh\OneDrive\Desktop\Open Source Engineer\backend")

models_init = """from .repository import Repository
from .issue import Issue
from .pull_request import PullRequest
from .agent_run import AgentRun
from .execution_log import ExecutionLog
from .repository_knowledge import RepositoryKnowledge
from .feedback import Feedback
from .embedding import Embedding

__all__ = [
    "Repository", "Issue", "PullRequest", "AgentRun",
    "ExecutionLog", "RepositoryKnowledge", "Feedback", "Embedding"
]
"""

repository_py = """import uuid
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
"""

issue_py = """import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base

class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repository_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repositories.id"))
    github_issue_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str | None] = mapped_column(String, nullable=True)
    labels: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    complexity_tier: Mapped[str | None] = mapped_column(String, nullable=True) # SENIOR, STAFF, INNOVATION
    difficulty_score: Mapped[float] = mapped_column(Float, default=0.0) # 1-10
    merge_probability_score: Mapped[float] = mapped_column(Float, default=0.0) # 0-100
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    composite_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    status: Mapped[str] = mapped_column(String, default="discovered") # discovered, analyzing, in_progress, pr_created, completed, skipped
    skip_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    assigned_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    repository = relationship("Repository", back_populates="issues")
    pull_requests = relationship("PullRequest", back_populates="issue")
    agent_runs = relationship("AgentRun", back_populates="issue")
"""

pull_request_py = """import uuid
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
"""

agent_run_py = """import uuid
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
"""

execution_log_py = """import uuid
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
"""

repository_knowledge_py = """import uuid
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
"""

feedback_py = """import uuid
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
"""

embedding_py = """import uuid
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
"""

def write_file(path, content):
    with open(BASE_DIR / path, 'w', encoding='utf-8') as f:
        f.write(content)

write_file('models/__init__.py', models_init)
write_file('models/repository.py', repository_py)
write_file('models/issue.py', issue_py)
write_file('models/pull_request.py', pull_request_py)
write_file('models/agent_run.py', agent_run_py)
write_file('models/execution_log.py', execution_log_py)
write_file('models/repository_knowledge.py', repository_knowledge_py)
write_file('models/feedback.py', feedback_py)
write_file('models/embedding.py', embedding_py)
