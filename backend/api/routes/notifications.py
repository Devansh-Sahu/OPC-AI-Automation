# backend/api/routes/notifications.py
"""
Notification management routes.

Endpoints:
  POST /notifications/test    — send test notification
  GET  /notifications/history — notification history
  PUT  /notifications/config  — update notification settings
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from backend.api.deps import get_secrets_manager, verify_api_key, SecretsManager
from backend.core.config import settings as app_settings

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory notification history (replace with DB model in production)
_NOTIFICATION_HISTORY: List[Dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class NotificationConfig(BaseModel):
    slack_webhook_url: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    email: Optional[str] = None
    notify_on_pr_created: bool = True
    notify_on_pr_merged: bool = True
    notify_on_agent_error: bool = True
    notify_on_discovery_complete: bool = False
    notify_on_pr_rejected: bool = True
    minimum_merge_probability_for_alert: float = Field(0.7, ge=0.0, le=1.0)


class NotificationConfigResponse(NotificationConfig):
    slack_configured: bool
    discord_configured: bool
    email_configured: bool


class TestNotificationRequest(BaseModel):
    message: Optional[str] = Field(None, description="Custom test message")
    channels: Optional[List[str]] = Field(None, description="slack|discord|email; omit for all")


class NotificationResult(BaseModel):
    channel: str
    success: bool
    message: str
    timestamp: datetime


class TestNotificationResponse(BaseModel):
    results: List[NotificationResult]
    overall_success: bool


class NotificationHistoryItem(BaseModel):
    id: str
    channel: str
    event_type: str
    message: str
    success: bool
    sent_at: datetime
    metadata: Optional[Dict[str, Any]]


class NotificationConfigUpdate(BaseModel):
    slack_webhook_url: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    email: Optional[str] = None
    notify_on_pr_created: Optional[bool] = None
    notify_on_pr_merged: Optional[bool] = None
    notify_on_agent_error: Optional[bool] = None
    notify_on_discovery_complete: Optional[bool] = None
    notify_on_pr_rejected: Optional[bool] = None
    minimum_merge_probability_for_alert: Optional[float] = Field(None, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _send_to_slack(url: str, message: str) -> bool:
    """Send a message to a Slack webhook URL."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"text": message})
            return resp.status_code == 200
    except Exception as exc:
        logger.error("Slack notification failed: %s", exc)
        return False


async def _send_to_discord(url: str, message: str) -> bool:
    """Send a message to a Discord webhook URL."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"content": message})
            return resp.status_code in (200, 204)
    except Exception as exc:
        logger.error("Discord notification failed: %s", exc)
        return False


def _record_notification(channel: str, event_type: str, message: str, success: bool, metadata: Optional[dict] = None) -> None:
    """Record a notification in the in-memory history."""
    _NOTIFICATION_HISTORY.append({
        "id": str(uuid4()),
        "channel": channel,
        "event_type": event_type,
        "message": message,
        "success": success,
        "sent_at": datetime.utcnow(),
        "metadata": metadata or {},
    })
    # Keep last 1000 entries
    if len(_NOTIFICATION_HISTORY) > 1000:
        _NOTIFICATION_HISTORY.pop(0)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/test", response_model=TestNotificationResponse, summary="Send test notification")
async def test_notifications(
    request: TestNotificationRequest,
    secrets: SecretsManager = Depends(get_secrets_manager),
    _key: str = Depends(verify_api_key),
) -> TestNotificationResponse:
    """Send a test notification to all configured (or specified) channels."""
    test_msg = request.message or "🤖 OpenSource AI Engineer — test notification! Everything is working."
    channels = request.channels or ["slack", "discord"]

    results: List[NotificationResult] = []

    if "slack" in channels:
        slack_url = secrets.get_secret("SLACK_WEBHOOK_URL")
        if slack_url:
            ok = await _send_to_slack(slack_url, test_msg)
            _record_notification("slack", "test", test_msg, ok)
            results.append(NotificationResult(
                channel="slack",
                success=ok,
                message="Sent successfully" if ok else "Failed to send",
                timestamp=datetime.utcnow(),
            ))
        else:
            results.append(NotificationResult(
                channel="slack",
                success=False,
                message="Slack webhook not configured",
                timestamp=datetime.utcnow(),
            ))

    if "discord" in channels:
        discord_url = secrets.get_secret("DISCORD_WEBHOOK_URL")
        if discord_url:
            ok = await _send_to_discord(discord_url, test_msg)
            _record_notification("discord", "test", test_msg, ok)
            results.append(NotificationResult(
                channel="discord",
                success=ok,
                message="Sent successfully" if ok else "Failed to send",
                timestamp=datetime.utcnow(),
            ))
        else:
            results.append(NotificationResult(
                channel="discord",
                success=False,
                message="Discord webhook not configured",
                timestamp=datetime.utcnow(),
            ))

    overall = any(r.success for r in results)
    return TestNotificationResponse(results=results, overall_success=overall)


@router.get("/history", response_model=List[NotificationHistoryItem], summary="Notification history")
async def get_notification_history(
    limit: int = Query(50, ge=1, le=500),
    channel: Optional[str] = Query(None, description="Filter by channel: slack|discord|email"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    _key: str = Depends(verify_api_key),
) -> List[NotificationHistoryItem]:
    """Return recent notification history."""
    history = _NOTIFICATION_HISTORY.copy()
    if channel:
        history = [h for h in history if h["channel"] == channel]
    if event_type:
        history = [h for h in history if h["event_type"] == event_type]
    # Most recent first
    history = list(reversed(history))[:limit]
    return [NotificationHistoryItem(**h) for h in history]


@router.put("/config", response_model=NotificationConfigResponse, summary="Update notification settings")
async def update_notification_config(
    payload: NotificationConfigUpdate,
    secrets: SecretsManager = Depends(get_secrets_manager),
    _key: str = Depends(verify_api_key),
) -> NotificationConfigResponse:
    """Update notification channel configuration."""
    if payload.slack_webhook_url is not None:
        secrets.store_secret("SLACK_WEBHOOK_URL", payload.slack_webhook_url)
    if payload.discord_webhook_url is not None:
        secrets.store_secret("DISCORD_WEBHOOK_URL", payload.discord_webhook_url)
    if payload.email is not None:
        secrets.store_secret("NOTIFICATION_EMAIL", payload.email)

    # Update non-sensitive flags in app_settings
    flag_map = {
        "notify_on_pr_created": "NOTIFY_ON_PR_CREATED",
        "notify_on_pr_merged": "NOTIFY_ON_PR_MERGED",
        "notify_on_agent_error": "NOTIFY_ON_AGENT_ERROR",
        "notify_on_discovery_complete": "NOTIFY_ON_DISCOVERY_COMPLETE",
        "notify_on_pr_rejected": "NOTIFY_ON_PR_REJECTED",
        "minimum_merge_probability_for_alert": "MIN_MERGE_PROB_ALERT",
    }
    for field, attr in flag_map.items():
        val = getattr(payload, field, None)
        if val is not None:
            try:
                setattr(app_settings, attr, val)
            except Exception:
                pass

    # Return current config
    slack = secrets.get_secret("SLACK_WEBHOOK_URL")
    discord = secrets.get_secret("DISCORD_WEBHOOK_URL")
    email = secrets.get_secret("NOTIFICATION_EMAIL")

    return NotificationConfigResponse(
        slack_webhook_url=None,  # Don't expose URL
        discord_webhook_url=None,
        email=None,
        notify_on_pr_created=getattr(app_settings, "NOTIFY_ON_PR_CREATED", True),
        notify_on_pr_merged=getattr(app_settings, "NOTIFY_ON_PR_MERGED", True),
        notify_on_agent_error=getattr(app_settings, "NOTIFY_ON_AGENT_ERROR", True),
        notify_on_discovery_complete=getattr(app_settings, "NOTIFY_ON_DISCOVERY_COMPLETE", False),
        notify_on_pr_rejected=getattr(app_settings, "NOTIFY_ON_PR_REJECTED", True),
        minimum_merge_probability_for_alert=getattr(app_settings, "MIN_MERGE_PROB_ALERT", 0.7),
        slack_configured=bool(slack),
        discord_configured=bool(discord),
        email_configured=bool(email),
    )
