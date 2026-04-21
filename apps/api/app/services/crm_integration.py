"""CRM integration service: webhooks and external API.

Sends training completion data to configured webhook URL.
Provides external API for CRM systems to query manager progress.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import ManagerProgress
from app.models.user import Team, User

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT = 10  # seconds

_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "postgres", "redis", "api", "web", "embeddings"}


def _validate_webhook_url(url: str) -> str:
    """Validate webhook URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed.")

    hostname = parsed.hostname or ""
    if hostname.lower() in _BLOCKED_HOSTS:
        raise ValueError(f"Blocked hostname: {hostname}")

    # Check for private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"Private/internal IP not allowed: {hostname}")
    except ValueError as exc:
        # If the ValueError came from our own raise, re-raise it
        if "not allowed" in str(exc) or "Blocked" in str(exc):
            raise
        # Otherwise hostname is not an IP address — that's fine (it's a domain name)

    return url


def generate_api_key() -> str:
    """Generate a secure API key for external CRM access."""
    return f"vh_{secrets.token_urlsafe(32)}"


def format_webhook_payload(
    user: User,
    session_data: dict,
    progress: ManagerProgress | None,
) -> dict:
    """Format standardized webhook payload for CRM systems.

    Compatible with Bitrix24, amoCRM, and generic webhook receivers.
    """
    return {
        "event": "training.completed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": "Hunter888",
        "manager": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
        },
        "session": {
            "id": session_data.get("session_id"),
            "score_total": session_data.get("score_total"),
            "duration_seconds": session_data.get("duration_seconds"),
            "scenario": session_data.get("scenario"),
            "archetype": session_data.get("archetype"),
            "status": session_data.get("status", "completed"),
        },
        "progress": {
            "level": progress.current_level if progress else 1,
            "total_xp": progress.total_xp if progress else 0,
            "skills": {
                "empathy": progress.skill_empathy if progress else 50,
                "knowledge": progress.skill_knowledge if progress else 50,
                "objection_handling": progress.skill_objection_handling if progress else 50,
                "stress_resistance": progress.skill_stress_resistance if progress else 50,
                "closing": progress.skill_closing if progress else 50,
                "qualification": progress.skill_qualification if progress else 50,
            },
            "total_sessions": progress.total_sessions if progress else 0,
        } if progress else None,
    }


async def send_training_webhook(
    user_id: uuid.UUID,
    session_data: dict,
    webhook_url: str,
    webhook_secret: str | None = None,
    db: AsyncSession | None = None,
) -> bool:
    """Send training completion webhook to configured URL.

    Returns True if webhook was successfully delivered.
    """
    if not webhook_url:
        return False

    # SSRF protection: validate URL before making the request
    try:
        _validate_webhook_url(webhook_url)
    except ValueError as e:
        logger.warning("Webhook URL rejected (SSRF protection): %s — %s", webhook_url, e)
        return False

    # Fetch user and progress
    user = None
    progress = None
    if db:
        user_r = await db.execute(select(User).where(User.id == user_id))
        user = user_r.scalar_one_or_none()
        progress_r = await db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == user_id)
        )
        progress = progress_r.scalar_one_or_none()

    if not user:
        logger.warning("Webhook skipped: user %s not found", user_id)
        return False

    payload = format_webhook_payload(user, session_data, progress)

    headers = {"Content-Type": "application/json"}
    if webhook_secret:
        import json
        body = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            webhook_secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            resp = await client.post(webhook_url, json=payload, headers=headers)
            if resp.status_code < 300:
                logger.info("Webhook delivered to %s (status=%d)", webhook_url, resp.status_code)
                return True
            else:
                logger.warning("Webhook failed: %s returned %d", webhook_url, resp.status_code)
                return False
    except Exception as e:
        logger.error("Webhook delivery error to %s: %s", webhook_url, e)
        return False


async def get_manager_progress_for_external(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict | None:
    """Get manager progress data formatted for external CRM API."""
    user_r = await db.execute(select(User).where(User.id == user_id))
    user = user_r.scalar_one_or_none()
    if not user:
        return None

    progress_r = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user_id)
    )
    progress = progress_r.scalar_one_or_none()

    return {
        "manager": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
        },
        "progress": {
            "level": progress.current_level if progress else 1,
            "total_xp": progress.total_xp if progress else 0,
            "total_sessions": progress.total_sessions if progress else 0,
            "skills": {
                "empathy": progress.skill_empathy if progress else 50,
                "knowledge": progress.skill_knowledge if progress else 50,
                "objection_handling": progress.skill_objection_handling if progress else 50,
                "stress_resistance": progress.skill_stress_resistance if progress else 50,
                "closing": progress.skill_closing if progress else 50,
                "qualification": progress.skill_qualification if progress else 50,
            },
        } if progress else None,
        "arena": {
            "answer_streak": progress.arena_best_answer_streak if progress else 0,
            "daily_streak": progress.arena_daily_streak if progress else 0,
        } if progress else None,
    }
