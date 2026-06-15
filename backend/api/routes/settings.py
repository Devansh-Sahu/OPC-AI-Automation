# backend/api/routes/settings.py
"""
Application settings management routes.

Endpoints:
  GET  /settings               — get current (non-sensitive) settings
  PUT  /settings               — update settings
  POST /settings/test-notification — test notification channels
  POST /settings/test-llm      — test LLM connection
  POST /settings/test-github   — test GitHub token
  GET  /settings/llm-models    — list available LLM models
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr

from backend.api.deps import get_secrets_manager, verify_api_key, SecretsManager
from backend.core.config import settings as app_settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# Available LLM models catalogue
# ---------------------------------------------------------------------------

LLM_MODELS = [
    {
        "id": "gemini-2.0-flash-exp",
        "provider": "google",
        "display_name": "Gemini 2.0 Flash (Experimental)",
        "context_window": 1_000_000,
        "cost_per_1m_tokens_usd": 0.0,
        "free_tier": True,
        "recommended": True,
    },
    {
        "id": "gemini-1.5-pro",
        "provider": "google",
        "display_name": "Gemini 1.5 Pro",
        "context_window": 2_000_000,
        "cost_per_1m_tokens_usd": 3.5,
        "free_tier": False,
        "recommended": False,
    },
    {
        "id": "gemini-1.5-flash",
        "provider": "google",
        "display_name": "Gemini 1.5 Flash",
        "context_window": 1_000_000,
        "cost_per_1m_tokens_usd": 0.075,
        "free_tier": False,
        "recommended": False,
    },
    {
        "id": "ollama/deepseek-coder-v2",
        "provider": "ollama",
        "display_name": "DeepSeek Coder V2 (Local)",
        "context_window": 128_000,
        "cost_per_1m_tokens_usd": 0.0,
        "free_tier": True,
        "recommended": False,
    },
    {
        "id": "ollama/llama3.1:8b",
        "provider": "ollama",
        "display_name": "Llama 3.1 8B (Local)",
        "context_window": 131_072,
        "cost_per_1m_tokens_usd": 0.0,
        "free_tier": True,
        "recommended": False,
    },
    {
        "id": "ollama/codestral",
        "provider": "ollama",
        "display_name": "Codestral (Local)",
        "context_window": 32_000,
        "cost_per_1m_tokens_usd": 0.0,
        "free_tier": True,
        "recommended": False,
    },
]


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class AppSettings(BaseModel):
    """Non-sensitive application settings returned to the frontend."""
    github_token_configured: bool
    github_webhook_secret_configured: bool
    default_llm_model: str
    ollama_base_url: Optional[str]
    max_concurrent_agents: int
    auto_approve_prs: bool
    min_merge_probability_threshold: float
    discovery_schedule_cron: Optional[str]
    notification_slack_configured: bool
    notification_discord_configured: bool
    notification_email_configured: bool
    max_repos_per_discovery: int
    agent_timeout_seconds: int
    working_dir: str


class SettingsUpdateRequest(BaseModel):
    default_llm_model: Optional[str] = None
    ollama_base_url: Optional[str] = None
    max_concurrent_agents: Optional[int] = Field(None, ge=1, le=20)
    auto_approve_prs: Optional[bool] = None
    min_merge_probability_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    discovery_schedule_cron: Optional[str] = None
    max_repos_per_discovery: Optional[int] = Field(None, ge=10, le=1000)
    agent_timeout_seconds: Optional[int] = Field(None, ge=60, le=7200)
    github_token: Optional[str] = None
    github_webhook_secret: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    notification_email: Optional[str] = None


class SettingsUpdateResponse(BaseModel):
    message: str
    updated_fields: List[str]


class TestResult(BaseModel):
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class LLMModel(BaseModel):
    id: str
    provider: str
    display_name: str
    context_window: int
    cost_per_1m_tokens_usd: float
    free_tier: bool
    recommended: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=AppSettings, summary="Get current application settings")
async def get_settings(
    secrets: SecretsManager = Depends(get_secrets_manager),
    _key: str = Depends(verify_api_key),
) -> AppSettings:
    """Return all non-sensitive application settings."""
    github_token = secrets.get_secret("GITHUB_TOKEN") or app_settings.GITHUB_TOKEN
    webhook_secret = secrets.get_secret("GITHUB_WEBHOOK_SECRET") or app_settings.GITHUB_WEBHOOK_SECRET
    slack = secrets.get_secret("SLACK_WEBHOOK_URL")
    discord = secrets.get_secret("DISCORD_WEBHOOK_URL")
    email = secrets.get_secret("NOTIFICATION_EMAIL")

    return AppSettings(
        github_token_configured=bool(github_token),
        github_webhook_secret_configured=bool(webhook_secret),
        default_llm_model=getattr(app_settings, "DEFAULT_LLM_MODEL", "gemini-2.0-flash-exp"),
        ollama_base_url=getattr(app_settings, "OLLAMA_BASE_URL", None),
        max_concurrent_agents=getattr(app_settings, "MAX_CONCURRENT_AGENTS", 3),
        auto_approve_prs=getattr(app_settings, "AUTO_APPROVE_PRS", False),
        min_merge_probability_threshold=getattr(app_settings, "MIN_MERGE_PROBABILITY", 0.65),
        discovery_schedule_cron=getattr(app_settings, "DISCOVERY_CRON", None),
        notification_slack_configured=bool(slack),
        notification_discord_configured=bool(discord),
        notification_email_configured=bool(email),
        max_repos_per_discovery=getattr(app_settings, "MAX_REPOS_PER_DISCOVERY", 200),
        agent_timeout_seconds=getattr(app_settings, "AGENT_TIMEOUT_SECONDS", 1800),
        working_dir=getattr(app_settings, "WORKING_DIR", "/tmp/ose-workspace"),
    )


@router.put("", response_model=SettingsUpdateResponse, summary="Update application settings")
async def update_settings(
    payload: SettingsUpdateRequest,
    secrets: SecretsManager = Depends(get_secrets_manager),
    _key: str = Depends(verify_api_key),
) -> SettingsUpdateResponse:
    """Update settings — sensitive values are encrypted and stored via SecretsManager."""
    updated: List[str] = []

    # Sensitive — store encrypted
    if payload.github_token is not None:
        secrets.store_secret("GITHUB_TOKEN", payload.github_token)
        updated.append("github_token")
    if payload.github_webhook_secret is not None:
        secrets.store_secret("GITHUB_WEBHOOK_SECRET", payload.github_webhook_secret)
        updated.append("github_webhook_secret")
    if payload.slack_webhook_url is not None:
        secrets.store_secret("SLACK_WEBHOOK_URL", payload.slack_webhook_url)
        updated.append("slack_webhook_url")
    if payload.discord_webhook_url is not None:
        secrets.store_secret("DISCORD_WEBHOOK_URL", payload.discord_webhook_url)
        updated.append("discord_webhook_url")
    if payload.notification_email is not None:
        secrets.store_secret("NOTIFICATION_EMAIL", payload.notification_email)
        updated.append("notification_email")

    # Non-sensitive — update app_settings attributes directly (runtime-only; add DB persistence as needed)
    non_sensitive = {
        "default_llm_model": "DEFAULT_LLM_MODEL",
        "ollama_base_url": "OLLAMA_BASE_URL",
        "max_concurrent_agents": "MAX_CONCURRENT_AGENTS",
        "auto_approve_prs": "AUTO_APPROVE_PRS",
        "min_merge_probability_threshold": "MIN_MERGE_PROBABILITY",
        "discovery_schedule_cron": "DISCOVERY_CRON",
        "max_repos_per_discovery": "MAX_REPOS_PER_DISCOVERY",
        "agent_timeout_seconds": "AGENT_TIMEOUT_SECONDS",
    }
    for field, attr in non_sensitive.items():
        val = getattr(payload, field)
        if val is not None:
            try:
                setattr(app_settings, attr, val)
                updated.append(field)
            except Exception as exc:
                logger.warning("Could not set setting %s: %s", attr, exc)

    if not updated:
        raise HTTPException(status_code=400, detail="No settings were provided to update")

    return SettingsUpdateResponse(message="Settings updated", updated_fields=updated)


@router.post("/test-notification", response_model=TestResult, summary="Send test notification")
async def test_notification(
    secrets: SecretsManager = Depends(get_secrets_manager),
    _key: str = Depends(verify_api_key),
) -> TestResult:
    """Send a test notification to all configured channels."""
    results: Dict[str, Any] = {}
    success = False

    slack_url = secrets.get_secret("SLACK_WEBHOOK_URL")
    if slack_url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(slack_url, json={"text": "🤖 OpenSource AI Engineer — test notification!"})
                results["slack"] = f"HTTP {resp.status_code}"
                if resp.status_code == 200:
                    success = True
        except Exception as exc:
            results["slack"] = f"Error: {exc}"

    discord_url = secrets.get_secret("DISCORD_WEBHOOK_URL")
    if discord_url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(discord_url, json={"content": "🤖 OpenSource AI Engineer — test notification!"})
                results["discord"] = f"HTTP {resp.status_code}"
                if resp.status_code in (200, 204):
                    success = True
        except Exception as exc:
            results["discord"] = f"Error: {exc}"

    if not slack_url and not discord_url:
        return TestResult(success=False, message="No notification channels configured", details={})

    return TestResult(
        success=success,
        message="Test notification sent" if success else "Test notification failed on all channels",
        details=results,
    )


@router.post("/test-llm", response_model=TestResult, summary="Test LLM connection")
async def test_llm(
    model: str = "gemini-2.0-flash-exp",
    secrets: SecretsManager = Depends(get_secrets_manager),
    _key: str = Depends(verify_api_key),
) -> TestResult:
    """Test the LLM connection by sending a simple ping prompt."""
    try:
        if model.startswith("ollama/"):
            import httpx
            ollama_base = getattr(app_settings, "OLLAMA_BASE_URL", "http://localhost:11434")
            model_name = model.replace("ollama/", "")
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{ollama_base}/api/generate",
                    json={"model": model_name, "prompt": "Say: pong", "stream": False},
                )
            if resp.status_code == 200:
                data = resp.json()
                return TestResult(
                    success=True,
                    message=f"Ollama '{model_name}' responded successfully",
                    details={"response_preview": data.get("response", "")[:100]},
                )
            else:
                return TestResult(success=False, message=f"Ollama returned HTTP {resp.status_code}")
        else:
            import google.generativeai as genai
            api_key = secrets.get_secret("GOOGLE_API_KEY") or getattr(app_settings, "GOOGLE_API_KEY", "")
            genai.configure(api_key=api_key)
            llm = genai.GenerativeModel(model)
            response = llm.generate_content("Say: pong")
            return TestResult(
                success=True,
                message=f"Gemini '{model}' responded successfully",
                details={"response_preview": response.text[:100]},
            )
    except Exception as exc:
        return TestResult(success=False, message=str(exc))


@router.post("/test-github", response_model=TestResult, summary="Test GitHub token")
async def test_github(
    secrets: SecretsManager = Depends(get_secrets_manager),
    _key: str = Depends(verify_api_key),
) -> TestResult:
    """Verify the GitHub token by fetching the authenticated user."""
    token = secrets.get_secret("GITHUB_TOKEN") or getattr(app_settings, "GITHUB_TOKEN", "")
    if not token:
        return TestResult(success=False, message="GitHub token not configured")
    try:
        import httpx
        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=10,
        ) as client:
            resp = await client.get("https://api.github.com/user")
        if resp.status_code == 200:
            data = resp.json()
            rl_resp = await client.get("https://api.github.com/rate_limit") if False else resp  # re-use client
            return TestResult(
                success=True,
                message=f"Authenticated as @{data.get('login')}",
                details={
                    "login": data.get("login"),
                    "name": data.get("name"),
                    "public_repos": data.get("public_repos"),
                },
            )
        else:
            return TestResult(success=False, message=f"GitHub returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        return TestResult(success=False, message=str(exc))


@router.get("/llm-models", response_model=List[LLMModel], summary="List available LLM models")
async def list_llm_models(
    _key: str = Depends(verify_api_key),
) -> List[LLMModel]:
    """Return the catalogue of available LLM models."""
    return [LLMModel(**m) for m in LLM_MODELS]
