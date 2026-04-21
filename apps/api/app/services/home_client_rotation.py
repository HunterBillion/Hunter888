"""Home page client rotation — generates a "waiting" AI client per user, rotates hourly.

The waiting client creates urgency: "this client is here now, talk to them before they leave."
No visible countdown — the client simply changes when the Redis key expires (~1 hour).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.redis_pool import get_redis
from app.models.scenario import Scenario

logger = logging.getLogger(__name__)

_ROTATION_TTL = 3600  # 1 hour
_REDIS_PREFIX = "home:client:"


def _redis_key(user_id: uuid.UUID) -> str:
    return f"{_REDIS_PREFIX}{user_id}"


async def get_waiting_client(user_id: uuid.UUID, db: AsyncSession) -> dict[str, Any] | None:
    """Return the current waiting client for this user.

    If a cached client exists in Redis — return it.
    If not — generate a new one, cache it, return preview.
    """
    r = get_redis()

    # Try cache first
    try:
        cached = await r.get(_redis_key(user_id))
        if cached:
            data = json.loads(cached)
            return data.get("preview")
    except Exception:
        logger.warning("Redis unavailable for home client rotation, generating fresh")

    # Generate new waiting client
    return await _generate_and_cache(user_id, db)


async def _generate_and_cache(user_id: uuid.UUID, db: AsyncSession) -> dict[str, Any] | None:
    """Generate a new waiting client, cache full profile + preview in Redis."""
    from app.services.difficulty import get_recommended_scenarios
    from app.services.client_generator import generate_client, get_crm_card

    # Pick a scenario from recommendations
    try:
        recs = await get_recommended_scenarios(user_id, db, count=3)
    except Exception:
        recs = []

    scenario = None
    scenario_id = None
    archetype_code = "skeptic"
    difficulty = 5

    if recs:
        # Pick the first (highest priority) recommendation
        rec = recs[0]
        scenario_id = rec.scenario_id
        archetype_code = rec.archetype_slug or "skeptic"
        difficulty = rec.difficulty or 5

        if scenario_id:
            result = await db.execute(
                select(Scenario).where(Scenario.id == scenario_id)
            )
            scenario = result.scalar_one_or_none()

    # Fallback: pick any active scenario WITH A CHARACTER.
    # Scenarios without character_id cause role reversal (AI plays manager).
    if not scenario:
        result = await db.execute(
            select(Scenario)
            .where(Scenario.is_active.is_(True))
            .where(Scenario.character_id.is_not(None))
            .limit(1)
        )
        scenario = result.scalar_one_or_none()
        if scenario:
            scenario_id = scenario.id

    if not scenario:
        logger.warning("No scenarios available for home client rotation")
        return None

    # Generate client profile
    try:
        profile = await generate_client(
            archetype_code=archetype_code,
            difficulty=difficulty,
            manager_level=1,
            lead_source="cold_base",
        )
    except Exception as e:
        logger.error("Failed to generate waiting client: %s", e)
        return None

    # Build preview (safe subset — no hidden data)
    preview = {
        "full_name": profile.full_name,
        "age": profile.age,
        "gender": profile.gender,
        "city": profile.city,
        "archetype_code": profile.archetype_code,
        "lead_source": profile.lead_source,
        "trust_level": profile.trust_level,
        "total_debt": profile.total_debt,
        "scenario_id": str(scenario_id),
        "difficulty": difficulty,
    }

    # Cache full profile + preview in Redis
    cache_data = {
        "preview": preview,
        "profile": asdict(profile),
        "scenario_id": str(scenario_id),
        "archetype_code": archetype_code,
        "difficulty": difficulty,
    }

    try:
        r = get_redis()
        await r.setex(
            _redis_key(user_id),
            _ROTATION_TTL,
            json.dumps(cache_data, ensure_ascii=False, default=str),
        )
    except Exception:
        logger.warning("Failed to cache waiting client in Redis")

    return preview


async def consume_waiting_client(user_id: uuid.UUID) -> dict[str, Any] | None:
    """Read and delete the cached waiting client. Returns full data for session creation.

    Called when user clicks "Start" on /home. The client "leaves" after being consumed.
    Returns: {scenario_id, archetype_code, difficulty, profile} or None.
    """
    r = get_redis()
    key = _redis_key(user_id)

    try:
        cached = await r.get(key)
        if not cached:
            return None
        # Delete the key — client is consumed
        await r.delete(key)
        return json.loads(cached)
    except Exception:
        logger.warning("Failed to consume waiting client from Redis")
        return None
