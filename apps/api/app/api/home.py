"""Home page API — waiting client rotation + quick start.

GET  /home/waiting-client  — current rotating AI client for this user
POST /home/start           — start a session with the waiting client
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.consent import check_consent_accepted
from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.scenario import Scenario
from app.models.training import SessionStatus, TrainingSession
from app.models.user import User
from app.services.home_client_rotation import consume_waiting_client, get_waiting_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/home", tags=["home"])


@router.get("/waiting-client")
async def get_home_waiting_client(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current waiting AI client for this user.

    The client rotates approximately every hour (no visible timer).
    Returns a preview with name, city, archetype — no hidden data.
    """
    preview = await get_waiting_client(user.id, db)
    if not preview:
        return {"client": None, "message": "Нет доступных сценариев"}
    return {"client": preview}


@router.post("/start", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def start_home_session(
    request: Request,
    user: User = Depends(check_consent_accepted),
    db: AsyncSession = Depends(get_db),
):
    """Start a training session with the waiting client from /home.

    Consumes the cached client (they "leave" after you start).
    Creates a session with source="home" for tracking.
    """
    from app.services.session_manager import check_rate_limit

    # Consume the waiting client
    client_data = await consume_waiting_client(user.id)

    if not client_data:
        # Preview cache expired or was consumed by another tab. DO NOT fall
        # back to a random scenario — the user saw Client A in the preview
        # and clicking "Ответить" would silently start with Client B. That's
        # the bug users reported: "увидел одни данные, после клика — другие".
        #
        # Instead: tell the client to refresh, which triggers a fresh
        # /home/waiting-client call, re-generating a preview they'll see.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Клиент ушёл. Обнови страницу — новый клиент уже ждёт.",
        )

    scenario_id = uuid.UUID(client_data["scenario_id"])
    custom_params = {
        "source": "home",
        "archetype": client_data.get("archetype_code"),
        "difficulty": client_data.get("difficulty"),
        "waiting_client_profile": client_data.get("profile"),
    }

    # Verify scenario exists AND has a character (role definition source)
    result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = result.scalar_one_or_none()
    if not scenario:
        raise HTTPException(400, "Сценарий не найден")
    if not scenario.character_id:
        logger.warning(
            "Home session requested scenario %s without character — role reversal risk",
            scenario_id,
        )

    # Rate limit check
    await check_rate_limit(user.id, db)

    # Create session
    session = TrainingSession(
        user_id=user.id,
        scenario_id=scenario_id,
        status=SessionStatus.active,
        custom_params=custom_params,
        source="home",
    )
    db.add(session)
    await db.flush()

    # Persist the previewed client persona as the session's ClientProfile.
    # Without this, the WS handler at apps/api/app/ws/training.py:3091-3105
    # falls into its "first connection — generate from scratch" branch and
    # invents a NEW client (different name/city/debt) that overwrites what
    # the user saw on /home. Reproducible on prod 2026-04-27. The fix mints
    # a ClientProfile row so the WS handler's `existing_profile` branch
    # (lines 3064-3076) picks it up and the persona stays consistent end-
    # to-end (the previewed persona == the persona shown in pre-training
    # screen == the persona the AI plays).
    profile_dict = client_data.get("profile") or {}
    if profile_dict:
        try:
            from app.services.client_generator import persist_client_profile_from_dict
            await persist_client_profile_from_dict(
                session_id=session.id,
                profile_dict=profile_dict,
                db=db,
            )
        except Exception:
            # Defensive: if persistence fails (schema drift, FK race), log
            # loudly but don't 500 the start — WS handler will generate-
            # from-scratch as before. This branch is the regression alarm
            # if it ever fires (zero ClientProfile rows for source=home
            # sessions in monitoring = the fix is alive).
            logger.exception(
                "home.start: failed to persist previewed ClientProfile "
                "for session=%s — runtime will fall back to "
                "generate_client_profile and the previewed persona "
                "will be lost",
                session.id,
            )

    # Initialize Redis state (same pattern as POST /training/sessions)
    try:
        from app.core.redis_pool import get_redis
        import json
        from datetime import datetime, timezone

        r = get_redis()
        state = {
            "user_id": str(user.id),
            "scenario_id": str(scenario_id),
            "status": "active",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "message_count": 0,
            "last_activity": datetime.now(timezone.utc).isoformat(),
        }
        await r.setex(
            f"session:{session.id}:state",
            7200,
            json.dumps(state),
        )
        # Initialize emotion as cold
        await r.setex(f"session:{session.id}:emotion", 7200, "cold")
    except Exception as e:
        logger.warning("Redis init failed for home session %s: %s", session.id, e)

    logger.info(
        "Home session started: user=%s session=%s scenario=%s",
        user.id, session.id, scenario_id,
    )

    return {
        "id": str(session.id),
        "scenario_id": str(scenario_id),
        "status": "active",
        "source": "home",
    }
