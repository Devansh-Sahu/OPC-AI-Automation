from pydantic import BaseModel
from typing import Optional, Dict
from uuid import UUID
from datetime import datetime

class AgentRunBase(BaseModel):
    issue_id: UUID
    workflow_run_id: str
    current_step: str
    total_steps: int = 0
    status: str = "pending"
    cost_tokens: int = 0
    cost_usd: float = 0.0

class AgentRunCreate(AgentRunBase):
    pass

class AgentRunUpdate(BaseModel):
    current_step: Optional[str] = None
    total_steps: Optional[int] = None
    status: Optional[str] = None
    checkpoint_state_json: Optional[Dict] = None
    cost_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class AgentRunInDB(AgentRunBase):
    id: UUID
    checkpoint_state_json: Optional[Dict] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True
