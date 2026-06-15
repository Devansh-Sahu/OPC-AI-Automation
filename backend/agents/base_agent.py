"""
Base Agent - Abstract foundation for all 12 AI agents.
Provides: LangGraph StateGraph, PostgresSaver checkpointing, cost tracking, circuit breaker.
"""

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db, async_session
from backend.core.llm import chat_completion, count_tokens
from backend.core.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)


class BaseAgentState(TypedDict):
    """Common state fields shared by all agents."""
    agent_run_id: str
    agent_name: str
    current_step: str
    started_at: str
    completed_at: Optional[str]
    error: Optional[str]
    retry_count: int
    total_tokens_used: int
    total_cost_usd: float
    messages: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class AgentExecutionContext:
    """Tracks execution metrics for a single agent run."""

    def __init__(self, agent_name: str, run_id: str):
        self.agent_name = agent_name
        self.run_id = run_id
        self.started_at = datetime.now(timezone.utc)
        self.total_tokens = 0
        self.total_cost_usd = 0.0
        self.steps_completed: List[str] = []
        self.errors: List[str] = []

    def record_llm_call(self, tokens_used: int, cost_usd: float):
        self.total_tokens += tokens_used
        self.total_cost_usd += cost_usd

    def record_step(self, step_name: str):
        self.steps_completed.append(step_name)
        logger.info(f"[{self.agent_name}:{self.run_id}] Step completed: {step_name}")

    def record_error(self, error: str):
        self.errors.append(error)
        logger.error(f"[{self.agent_name}:{self.run_id}] Error: {error}")

    def elapsed_seconds(self) -> float:
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()


class BaseAgent(ABC):
    """
    Abstract base class for all OpenSource AI Engineer agents.

    Every agent:
    - Has a LangGraph StateGraph
    - Uses PostgresSaver for checkpointing (every node persisted)
    - Tracks token usage and USD cost
    - Uses circuit breaker for external calls
    - Logs all activity to execution_logs table
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.graph: Optional[StateGraph] = None
        self.compiled_graph = None
        self._execution_contexts: Dict[str, AgentExecutionContext] = {}
        self.logger = logging.getLogger(f"agents.{agent_name}")
        self._initialized = False

    async def initialize(self):
        """Initialize agent: build graph, set up checkpointer."""
        if self._initialized:
            return

        try:
            # Build the LangGraph state machine
            self.graph = self._build_graph()

            # Set up PostgresSaver checkpointer
            conn_string = settings.DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql://"
            ).replace("postgresql://", "postgresql://")

            self.checkpointer = AsyncPostgresSaver.from_conn_string(conn_string)
            await self.checkpointer.setup()

            # Compile graph with checkpointer
            self.compiled_graph = self.graph.compile(
                checkpointer=self.checkpointer,
                interrupt_before=self._get_interrupt_nodes(),
            )

            self._initialized = True
            self.logger.info(f"Agent {self.agent_name} initialized successfully")

        except Exception as e:
            self.logger.error(f"Failed to initialize agent {self.agent_name}: {e}")
            # Fall back to in-memory checkpointing if DB not available
            from langgraph.checkpoint.memory import MemorySaver
            self.checkpointer = MemorySaver()
            self.compiled_graph = self.graph.compile(
                checkpointer=self.checkpointer,
                interrupt_before=self._get_interrupt_nodes(),
            )
            self._initialized = True

    @abstractmethod
    def _build_graph(self) -> StateGraph:
        """Build and return the LangGraph StateGraph for this agent."""
        pass

    @abstractmethod
    async def run(self, input_data: Dict[str, Any], run_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute the agent with given input. Returns final state."""
        pass

    def _get_interrupt_nodes(self) -> List[str]:
        """Override to specify nodes that require human approval before execution."""
        return []

    def _new_run_id(self) -> str:
        return str(uuid.uuid4())

    def _create_context(self, run_id: str) -> AgentExecutionContext:
        ctx = AgentExecutionContext(self.agent_name, run_id)
        self._execution_contexts[run_id] = ctx
        return ctx

    def _get_context(self, run_id: str) -> Optional[AgentExecutionContext]:
        return self._execution_contexts.get(run_id)

    async def _call_llm(
        self,
        messages: List[Dict[str, str]],
        run_id: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: Optional[str] = None,
    ) -> str:
        """
        Call LLM with circuit breaker protection and cost tracking.
        Uses Gemini 2.5 Flash -> Ollama Qwen3 fallback via LiteLLM.
        """
        ctx = self._get_context(run_id)

        @circuit_breaker(name=f"{self.agent_name}_llm", failure_threshold=3, recovery_timeout=60)
        async def _do_call():
            kwargs = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}

            response = await chat_completion(**kwargs)
            return response

        try:
            result = await _do_call()
            content = result["choices"][0]["message"]["content"]

            # Track cost
            usage = result.get("usage", {})
            tokens_used = usage.get("total_tokens", 0)
            # Rough cost estimate: Gemini Flash ~$0.075/1M tokens
            cost = (tokens_used / 1_000_000) * 0.075

            if ctx:
                ctx.record_llm_call(tokens_used, cost)

            return content

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise

    async def _call_llm_json(
        self,
        messages: List[Dict[str, str]],
        run_id: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Call LLM expecting JSON response. Returns parsed dict."""
        response = await self._call_llm(
            messages=messages,
            run_id=run_id,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json",
        )
        try:
            # Strip markdown code fences if present
            clean = response.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1])
            return json.loads(clean)
        except json.JSONDecodeError as e:
            self.logger.warning(f"JSON parse failed, attempting extraction: {e}")
            # Try to extract JSON from response
            import re
            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Could not parse JSON from LLM response: {response[:200]}")

    async def _log_execution(
        self,
        run_id: str,
        step_name: str,
        status: str,
        details: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Log agent execution step to database."""
        try:
            async with async_session() as session:
                from backend.models.agent import AgentExecutionLog
                log_entry = AgentExecutionLog(
                    run_id=run_id,
                    agent_name=self.agent_name,
                    step_name=step_name,
                    status=status,
                    details=details or {},
                    error_message=error,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            # Don't fail the agent because of logging errors
            self.logger.warning(f"Failed to log execution: {e}")

    async def _update_run_status(
        self,
        run_id: str,
        status: str,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Update agent run status in database."""
        try:
            async with async_session() as session:
                from backend.models.agent import AgentRun
                from sqlalchemy import select, update
                stmt = (
                    update(AgentRun)
                    .where(AgentRun.run_id == run_id)
                    .values(
                        status=status,
                        result=result,
                        error_message=error,
                        completed_at=datetime.now(timezone.utc),
                    )
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            self.logger.warning(f"Failed to update run status: {e}")

    def _base_initial_state(self, run_id: str) -> BaseAgentState:
        """Create initial base state for a new run."""
        return BaseAgentState(
            agent_run_id=run_id,
            agent_name=self.agent_name,
            current_step="init",
            started_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            error=None,
            retry_count=0,
            total_tokens_used=0,
            total_cost_usd=0.0,
            messages=[],
            metadata={},
        )

    async def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a run by ID (from checkpoint)."""
        if not self.compiled_graph:
            return None
        config = {"configurable": {"thread_id": run_id}}
        state = await self.compiled_graph.aget_state(config)
        if state:
            return dict(state.values)
        return None

    async def resume_run(self, run_id: str, input_data: Optional[Dict] = None) -> Dict[str, Any]:
        """Resume a paused/interrupted run (e.g., after human approval)."""
        if not self.compiled_graph:
            raise RuntimeError("Agent not initialized")
        config = {"configurable": {"thread_id": run_id}}
        result = await self.compiled_graph.ainvoke(input_data or None, config=config)
        return result

    def get_cost_summary(self, run_id: str) -> Dict[str, Any]:
        """Get cost summary for a run."""
        ctx = self._get_context(run_id)
        if not ctx:
            return {"error": "Run not found"}
        return {
            "run_id": run_id,
            "agent_name": self.agent_name,
            "total_tokens": ctx.total_tokens,
            "total_cost_usd": round(ctx.total_cost_usd, 6),
            "elapsed_seconds": ctx.elapsed_seconds(),
            "steps_completed": ctx.steps_completed,
        }
