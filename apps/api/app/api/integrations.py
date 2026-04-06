"""REST API for CRM integrations.

Endpoints:
  GET  /integrations/settings             -- get webhook/API settings
  PUT  /integrations/settings             -- update webhook URL
  POST /integrations/test-webhook         -- send test webhook
  GET  /integrations/api-key              -- get/generate API key
  GET  /api/v1/external/manager/{id}/progress -- public API for CRM (API key auth)
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.core.redis_pool import get_redis
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

SETTINGS_KEY_PREFIX = "integration:settings:"
API_KEY_INDEX = "integration:api_keys"


async def _get_team_settings(team_id: uuid.UUID) -> dict:
    """Get integration settings from Redis."""
    redis = await get_redis()
    if not redis:
        return {}
    raw = await redis.get(f"{SETTINGS_KEY_PREFIX}{team_id}")
    return json.loads(raw) if raw else {}


async def _set_team_settings(team_id: uuid.UUID, settings: dict) -> None:
    """Save integration settings to Redis."""
    redis = await get_redis()
    if redis:
        await redis.set(f"{SETTINGS_KEY_PREFIX}{team_id}", json.dumps(settings))


# ═══════════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/settings")
async def get_integration_settings(
    user: User = Depends(require_role("rop", "admin")),
):
    """Get webhook and API integration settings."""
    if not user.team_id:
        return {"webhook_url": None, "is_webhook_enabled": False, "has_api_key": False}

    settings = await _get_team_settings(user.team_id)
    return {
        "webhook_url": settings.get("webhook_url"),
        "is_webhook_enabled": settings.get("is_webhook_enabled", False),
        "has_api_key": bool(settings.get("api_key")),
    }


@router.put("/settings")
@limiter.limit("5/minute")
async def update_integration_settings(
    request: Request,
    data: dict,
    user: User = Depends(require_role("rop", "admin")),
):
    """Update webhook URL and enable/disable."""
    if not user.team_id:
        raise HTTPException(status_code=400, detail="No team assigned")

    settings = await _get_team_settings(user.team_id)
    if "webhook_url" in data:
        settings["webhook_url"] = data["webhook_url"]
    if "is_webhook_enabled" in data:
        settings["is_webhook_enabled"] = data["is_webhook_enabled"]
    if "webhook_secret" in data:
        settings["webhook_secret"] = data["webhook_secret"]

    await _set_team_settings(user.team_id, settings)
    return {"message": "Settings updated"}


@router.post("/test-webhook")
@limiter.limit("3/minute")
async def test_webhook(
    request: Request,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Send a test webhook to the configured URL."""
    if not user.team_id:
        raise HTTPException(status_code=400, detail="No team assigned")

    settings = await _get_team_settings(user.team_id)
    webhook_url = settings.get("webhook_url")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="No webhook URL configured")

    from app.services.crm_integration import send_training_webhook

    test_data = {
        "session_id": "test-" + str(uuid.uuid4())[:8],
        "score_total": 75.0,
        "duration_seconds": 600,
        "scenario": "test_scenario",
        "archetype": "skeptic",
        "status": "test",
    }

    success = await send_training_webhook(
        user_id=user.id,
        session_data=test_data,
        webhook_url=webhook_url,
        webhook_secret=settings.get("webhook_secret"),
        db=db,
    )

    return {"success": success, "webhook_url": webhook_url}


# ═══════════════════════════════════════════════════════════════════════════
# API KEY
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/api-key")
async def get_or_create_api_key(
    user: User = Depends(require_role("rop", "admin")),
):
    """Get existing or generate new API key for external CRM access."""
    if not user.team_id:
        raise HTTPException(status_code=400, detail="No team assigned")

    settings = await _get_team_settings(user.team_id)

    if not settings.get("api_key"):
        from app.services.crm_integration import generate_api_key
        api_key = generate_api_key()
        settings["api_key"] = api_key
        await _set_team_settings(user.team_id, settings)

        # Index API key → team_id for lookup
        redis = await get_redis()
        if redis:
            await redis.hset(API_KEY_INDEX, api_key, str(user.team_id))
    else:
        api_key = settings["api_key"]

    return {"api_key": api_key}


# ═══════════════════════════════════════════════════════════════════════════
# EXTERNAL API (API key auth)
# ═══════════════════════════════════════════════════════════════════════════

async def _verify_api_key(x_api_key: str = Header(...)) -> uuid.UUID:
    """Verify API key and return team_id."""
    redis = await get_redis()
    if not redis:
        raise HTTPException(status_code=503, detail="Service unavailable")

    team_id_str = await redis.hget(API_KEY_INDEX, x_api_key)
    if not team_id_str:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return uuid.UUID(team_id_str)


@router.get("/v1/external/manager/{manager_id}/progress")
async def external_manager_progress(
    manager_id: uuid.UUID,
    team_id: uuid.UUID = Depends(_verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    """External API: get manager progress data for CRM integration.

    Authenticated via X-API-Key header (team-scoped).
    """
    # Verify manager belongs to team
    user_r = await db.execute(
        select(User).where(User.id == manager_id, User.team_id == team_id)
    )
    user = user_r.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Manager not found in your team")

    from app.services.crm_integration import get_manager_progress_for_external
    data = await get_manager_progress_for_external(manager_id, db)
    if not data:
        raise HTTPException(status_code=404, detail="No progress data")

    return data
