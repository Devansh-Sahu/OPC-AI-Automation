"""
backend/core/llm.py
───────────────────
LiteLLM router with a Gemini → Ollama → DeepSeek fallback chain.

Features:
- Async chat completion with automatic retry & fallback
- Token counting and USD cost tracking per request
- Task-aware model selection (code generation vs analysis)
- Streaming support
- Request/response logging to the execution context
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Optional

import litellm
from litellm import (
    Router,
    ModelResponse,
    completion_cost,
    token_counter,
)

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Silence LiteLLM's noisy default logging unless in debug mode
if not settings.DEBUG:
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


# ── Task types ────────────────────────────────────────────────────────────────

class TaskType(str, Enum):
    """LLM task categories that influence model selection."""

    CODE_GENERATION = "code_generation"    # Writing / patching code
    CODE_REVIEW = "code_review"            # Reviewing diff/PR
    ANALYSIS = "analysis"                  # Issue analysis, repo scoring
    SUMMARISATION = "summarisation"        # Summarising long documents
    PLANNING = "planning"                  # Agent planning / tool selection
    CLASSIFICATION = "classification"      # Short classification tasks


# ── Cost / usage tracking ─────────────────────────────────────────────────────

@dataclass
class LLMUsage:
    """Captures token counts and estimated cost for a single LLM call."""

    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    success: bool = True
    error: str = ""

    @property
    def summary(self) -> dict:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "latency_ms": self.latency_ms,
            "success": self.success,
        }


# Running totals (in-process; use Redis for multi-process)
_total_tokens: int = 0
_total_cost_usd: float = 0.0


def get_cumulative_usage() -> dict:
    """Return the running totals since process start."""
    return {
        "total_tokens": _total_tokens,
        "total_cost_usd": round(_total_cost_usd, 4),
    }


# ── Model definitions ─────────────────────────────────────────────────────────

def _build_router() -> Router:
    """Build the LiteLLM Router with fallback chain."""

    model_list: list[dict] = []

    # ── Primary: Gemini 2.5 Flash ─────────────────────────────────────────────
    if settings.GEMINI_API_KEY:
        model_list.append(
            {
                "model_name": "primary-fast",
                "litellm_params": {
                    "model": "gemini/gemini-2.5-flash",
                    "api_key": settings.GEMINI_API_KEY,
                    "timeout": settings.LLM_REQUEST_TIMEOUT,
                },
                "model_info": {"mode": "chat", "max_tokens": 8192},
            }
        )
        model_list.append(
            {
                "model_name": "primary-code",
                "litellm_params": {
                    "model": "gemini/gemini-2.5-flash",
                    "api_key": settings.GEMINI_API_KEY,
                    "timeout": settings.LLM_REQUEST_TIMEOUT,
                },
                "model_info": {"mode": "chat", "max_tokens": 8192},
            }
        )

    # ── Fallback 1: Ollama Qwen3 (local) ─────────────────────────────────────
    model_list.append(
        {
            "model_name": "fallback-local",
            "litellm_params": {
                "model": f"ollama/{settings.OLLAMA_MODEL}",
                "api_base": settings.OLLAMA_BASE_URL,
                "timeout": settings.LLM_REQUEST_TIMEOUT + 30,
            },
            "model_info": {"mode": "chat", "max_tokens": 8192},
        }
    )

    # ── Fallback 2: DeepSeek ──────────────────────────────────────────────────
    if settings.DEEPSEEK_API_KEY:
        model_list.append(
            {
                "model_name": "fallback-deepseek",
                "litellm_params": {
                    "model": "deepseek/deepseek-coder",
                    "api_key": settings.DEEPSEEK_API_KEY,
                    "api_base": settings.DEEPSEEK_BASE_URL,
                    "timeout": settings.LLM_REQUEST_TIMEOUT,
                },
                "model_info": {"mode": "chat", "max_tokens": 8192},
            }
        )

    # Ensure we always have at least one model entry
    if not model_list:
        logger.warning(
            "No LLM API keys configured. Using Ollama as sole provider."
        )

    router = Router(
        model_list=model_list,
        routing_strategy="latency-based-routing",
        num_retries=settings.LLM_MAX_RETRIES,
        retry_after=2,
        allowed_fails=2,
        cooldown_time=60,
        set_verbose=settings.DEBUG,
        fallbacks=[
            {"primary-fast": ["fallback-local", "fallback-deepseek"]},
            {"primary-code": ["fallback-local", "fallback-deepseek"]},
        ],
    )
    return router


# Module-level router (lazy initialised)
_router: Optional[Router] = None


def get_router() -> Router:
    """Return the singleton LiteLLM Router, building it on first call."""
    global _router
    if _router is None:
        _router = _build_router()
    return _router


# ── Model selection ────────────────────────────────────────────────────────────

_TASK_TO_MODEL: dict[TaskType, str] = {
    TaskType.CODE_GENERATION: "primary-code",
    TaskType.CODE_REVIEW: "primary-code",
    TaskType.ANALYSIS: "primary-fast",
    TaskType.SUMMARISATION: "primary-fast",
    TaskType.PLANNING: "primary-fast",
    TaskType.CLASSIFICATION: "primary-fast",
}

_TASK_TO_MAX_TOKENS: dict[TaskType, int] = {
    TaskType.CODE_GENERATION: settings.LLM_MAX_TOKENS_CODE,
    TaskType.CODE_REVIEW: settings.LLM_MAX_TOKENS_CODE,
    TaskType.ANALYSIS: settings.LLM_MAX_TOKENS_ANALYSIS,
    TaskType.SUMMARISATION: settings.LLM_MAX_TOKENS_ANALYSIS,
    TaskType.PLANNING: settings.LLM_MAX_TOKENS_ANALYSIS,
    TaskType.CLASSIFICATION: 512,
}


def select_model(task: TaskType) -> str:
    """Return the preferred model group name for a given task."""
    return _TASK_TO_MODEL.get(task, "primary-fast")


# ── Core completion function ──────────────────────────────────────────────────

async def chat_completion(
    messages: list[dict[str, str]],
    task: TaskType = TaskType.ANALYSIS,
    model_override: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    system_prompt: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> tuple[str, LLMUsage]:
    """Send a chat completion request through the LiteLLM fallback router.

    Args:
        messages:       List of ``{"role": ..., "content": ...}`` dicts.
        task:           Task type used to select model and max_tokens.
        model_override: Force a specific model group (bypasses task routing).
        temperature:    Sampling temperature (0.0–1.0).
        max_tokens:     Override default token limit for this task.
        system_prompt:  Prepend a system message if provided.
        metadata:       Extra metadata forwarded to LiteLLM (e.g. trace IDs).

    Returns:
        Tuple of (response_text, LLMUsage).
    """
    global _total_tokens, _total_cost_usd

    model_name = model_override or select_model(task)
    effective_max_tokens = max_tokens or _TASK_TO_MAX_TOKENS.get(
        task, settings.LLM_MAX_TOKENS_ANALYSIS
    )

    # Prepend system message
    full_messages = list(messages)
    if system_prompt:
        full_messages = [{"role": "system", "content": system_prompt}] + full_messages

    usage = LLMUsage()
    start_ts = time.monotonic()

    try:
        router = get_router()
        response: ModelResponse = await router.acompletion(
            model=model_name,
            messages=full_messages,
            temperature=temperature,
            max_tokens=effective_max_tokens,
            metadata=metadata or {},
        )

        elapsed_ms = int((time.monotonic() - start_ts) * 1000)
        choice = response.choices[0]
        content: str = choice.message.content or ""

        # ── Usage tracking ────────────────────────────────────────────────────
        resp_usage = getattr(response, "usage", None)
        if resp_usage:
            usage.prompt_tokens = getattr(resp_usage, "prompt_tokens", 0)
            usage.completion_tokens = getattr(resp_usage, "completion_tokens", 0)
            usage.total_tokens = getattr(resp_usage, "total_tokens", 0)
        else:
            # Fallback: count locally
            usage.prompt_tokens = token_counter(model=model_name, messages=full_messages)
            usage.completion_tokens = token_counter(
                model=model_name,
                messages=[{"role": "assistant", "content": content}],
            )
            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        usage.model = getattr(response, "model", model_name)
        usage.latency_ms = elapsed_ms
        usage.success = True

        # Estimate cost
        try:
            usage.cost_usd = completion_cost(completion_response=response)
        except Exception:
            usage.cost_usd = 0.0

        _total_tokens += usage.total_tokens
        _total_cost_usd += usage.cost_usd

        logger.debug(
            "LLM call complete | model=%s tokens=%d cost=$%.5f latency=%dms",
            usage.model,
            usage.total_tokens,
            usage.cost_usd,
            elapsed_ms,
        )

        return content, usage

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start_ts) * 1000)
        usage.success = False
        usage.error = str(exc)
        usage.latency_ms = elapsed_ms
        logger.error("LLM completion failed after %dms: %s", elapsed_ms, exc)
        raise


async def chat_completion_stream(
    messages: list[dict[str, str]],
    task: TaskType = TaskType.ANALYSIS,
    model_override: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    system_prompt: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Stream tokens from the LLM one chunk at a time.

    Yields:
        Individual text delta strings as they arrive.
    """
    model_name = model_override or select_model(task)
    effective_max_tokens = max_tokens or _TASK_TO_MAX_TOKENS.get(
        task, settings.LLM_MAX_TOKENS_ANALYSIS
    )

    full_messages = list(messages)
    if system_prompt:
        full_messages = [{"role": "system", "content": system_prompt}] + full_messages

    router = get_router()
    response = await router.acompletion(
        model=model_name,
        messages=full_messages,
        temperature=temperature,
        max_tokens=effective_max_tokens,
        stream=True,
    )

    async for chunk in response:
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            yield content


# ── Convenience wrappers ──────────────────────────────────────────────────────

async def generate_code(
    prompt: str,
    context: Optional[str] = None,
    language: str = "python",
) -> tuple[str, LLMUsage]:
    """Generate code for a given prompt.

    Args:
        prompt:   Detailed description of what to implement.
        context:  Optional surrounding code or file context.
        language: Target programming language (default: python).

    Returns:
        (generated_code_string, LLMUsage)
    """
    system = (
        f"You are an expert {language} software engineer. "
        "Write clean, idiomatic, well-documented code. "
        "Return only the code without markdown fences unless asked."
    )
    user_content = prompt
    if context:
        user_content = f"Context:\n```{language}\n{context}\n```\n\nTask:\n{prompt}"

    return await chat_completion(
        messages=[{"role": "user", "content": user_content}],
        task=TaskType.CODE_GENERATION,
        system_prompt=system,
        temperature=0.1,
    )


async def analyse_issue(issue_title: str, issue_body: str, repo_context: str) -> tuple[str, LLMUsage]:
    """Analyse a GitHub issue and produce a structured implementation plan."""
    system = (
        "You are a senior software architect. Analyse the GitHub issue and produce "
        "a detailed, actionable implementation plan in JSON format with keys: "
        "'summary', 'root_cause', 'approach', 'files_to_modify', "
        "'tests_required', 'estimated_complexity', 'risks'."
    )
    user = (
        f"Repository context:\n{repo_context}\n\n"
        f"Issue title: {issue_title}\n\n"
        f"Issue body:\n{issue_body}"
    )
    return await chat_completion(
        messages=[{"role": "user", "content": user}],
        task=TaskType.ANALYSIS,
        system_prompt=system,
        temperature=0.3,
    )


async def count_tokens(text: str, model: str = "gemini/gemini-2.5-flash") -> int:
    """Estimate the number of tokens in *text* for a given *model*."""
    try:
        return token_counter(model=model, messages=[{"role": "user", "content": text}])
    except Exception:
        # Rough approximation: 4 chars per token
        return len(text) // 4
