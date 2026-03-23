import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.consent import check_consent_accepted
from app.core import errors as err
from app.core.deps import get_current_user
from app.database import get_db
from app.core.deps import require_role
from app.models.roleplay import ClientStory
from app.models.training import AssignedTraining, Message, SessionStatus, TrainingSession
from app.models.scenario import Scenario
from app.models.user import User
from pydantic import BaseModel, Field, field_validator
from app.schemas.training import (
    HistoryEntryResponse,
    MessageResponse,
    SessionResponse,
    SessionResultResponse,
    SessionStartRequest,
    SoftSkillsResult,
    StoryCallSummary,
    StorySummaryResponse,
    TrapResultItem,
)
from app.services.gamification import check_and_award_achievements
from app.services.scoring import calculate_scores, generate_recommendations
from app.services.session_manager import (
    check_rate_limit as sm_check_rate_limit,
    end_session as sm_end_session,
    RateLimitError as SmRateLimitError,
)
from app.services.emotion import init_emotion as sm_init_emotion

logger = logging.getLogger(__name__)

router = APIRouter()


def _session_to_response(session: TrainingSession) -> SessionResponse:
    return SessionResponse.model_validate(session)


def _story_call_summary(session: TrainingSession) -> StoryCallSummary:
    return StoryCallSummary(
        session_id=session.id,
        call_number=session.call_number_in_story or 1,
        status=session.status.value if hasattr(session.status, "value") else str(session.status),
        started_at=session.started_at,
        ended_at=session.ended_at,
        duration_seconds=session.duration_seconds,
        score_total=session.score_total,
        score_human_factor=session.score_human_factor,
        score_narrative=session.score_narrative,
        score_legal=session.score_legal,
    )


def _story_to_summary(story: ClientStory, sessions: list[TrainingSession]) -> StorySummaryResponse:
    director_state = story.director_state or {}
    completed_sessions = [s for s in sessions if s.status == SessionStatus.completed]
    scored_sessions = [s.score_total for s in sessions if s.score_total is not None]
    latest_session = max(sessions, key=lambda s: s.started_at) if sessions else None
    tension_curve = director_state.get("tension_curve", []) or []

    return StorySummaryResponse(
        id=story.id,
        story_name=story.story_name,
        total_calls_planned=story.total_calls_planned,
        current_call_number=story.current_call_number,
        is_completed=story.is_completed,
        game_status=director_state.get("game_status", "new"),
        tension=float(tension_curve[-1]) if tension_curve else 0.0,
        tension_curve=[float(x) for x in tension_curve],
        pacing=director_state.get("pacing"),
        next_twist=director_state.get("next_twist"),
        active_factors=list(story.active_factors or []),
        between_call_events=list(story.between_call_events or []),
        consequences=list(story.consequences or []),
        started_at=story.started_at,
        ended_at=story.ended_at,
        created_at=story.created_at,
        completed_calls=len(completed_sessions),
        avg_score=round(sum(scored_sessions) / len(scored_sessions), 1) if scored_sessions else None,
        best_score=max(scored_sessions) if scored_sessions else None,
        latest_session_id=latest_session.id if latest_session else None,
    )


async def _load_story_context(
    db: AsyncSession,
    story_id: uuid.UUID | None,
    *,
    user_id: uuid.UUID,
) -> tuple[StorySummaryResponse | None, list[StoryCallSummary]]:
    if story_id is None:
        return None, []

    story_result = await db.execute(
        select(ClientStory).where(
            ClientStory.id == story_id,
            ClientStory.user_id == user_id,
        )
    )
    story = story_result.scalar_one_or_none()
    if story is None:
        return None, []

    sessions_result = await db.execute(
        select(TrainingSession)
        .where(
            TrainingSession.client_story_id == story_id,
            TrainingSession.user_id == user_id,
        )
        .order_by(TrainingSession.call_number_in_story.asc(), TrainingSession.started_at.asc())
    )
    story_sessions = list(sessions_result.scalars().all())
    return _story_to_summary(story, story_sessions), [_story_call_summary(s) for s in story_sessions]


async def _build_session_result(
    session: TrainingSession,
    *,
    user: User,
    db: AsyncSession,
) -> SessionResultResponse:
    messages_result = await db.execute(
        select(Message)
        .where(Message.session_id == session.id)
        .order_by(Message.sequence_number)
    )
    messages = messages_result.scalars().all()

    details = session.scoring_details or {}

    trap_results = None
    trap_handling = details.get("trap_handling", {})
    raw_traps = trap_handling.get("traps", [])
    if raw_traps:
        trap_results = [
            TrapResultItem(
                name=t.get("name", "Unknown"),
                caught=t.get("status") == "dodged",
                bonus=t.get("delta") if t.get("status") == "dodged" else None,
                penalty=abs(t.get("delta", 0)) if t.get("status") in ("fell", "partial") else None,
            )
            for t in raw_traps
            if t.get("status") != "not_activated"
        ] or None

    soft_skills = None
    user_msgs = [m for m in messages if m.role.value == "user"]
    assistant_msgs = [m for m in messages if m.role.value == "assistant"]
    if user_msgs:
        user_chars = sum(len(m.content) for m in user_msgs)
        asst_chars = sum(len(m.content) for m in assistant_msgs)
        total_chars = user_chars + asst_chars
        talk_ratio = round(user_chars / total_chars, 2) if total_chars > 0 else 0.5
        avg_msg_len = round(user_chars / len(user_msgs), 1)

        avg_response_time = 0.0
        if len(user_msgs) >= 2:
            timestamps = [m.created_at for m in user_msgs]
            gaps = [(timestamps[i] - timestamps[i - 1]).total_seconds() for i in range(1, len(timestamps))]
            avg_response_time = round(sum(gaps) / len(gaps), 1) if gaps else 0.0

        name_count = 0
        client_name = details.get("_client_name", "")
        if client_name:
            first_name = client_name.split()[0].lower()
            for m in user_msgs:
                if first_name in m.content.lower():
                    name_count += 1

        interruptions = 0
        for i in range(1, len(user_msgs)):
            gap = (user_msgs[i].created_at - user_msgs[i - 1].created_at).total_seconds()
            if gap < 5 and len(user_msgs[i].content) < 20:
                interruptions += 1

        soft_skills = SoftSkillsResult(
            avg_response_time_sec=avg_response_time,
            talk_listen_ratio=talk_ratio,
            name_usage_count=name_count,
            interruptions=interruptions,
            avg_message_length=avg_msg_len,
        )

    story, story_calls = await _load_story_context(db, session.client_story_id, user_id=user.id)
    return SessionResultResponse(
        session=_session_to_response(session),
        messages=[MessageResponse.model_validate(m) for m in messages],
        score_breakdown=session.scoring_details,
        trap_results=trap_results,
        soft_skills=soft_skills,
        client_card=details.get("_client_card_reveal"),
        story=story,
        story_calls=story_calls,
    )


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    body: SessionStartRequest,
    user: User = Depends(check_consent_accepted),
    db: AsyncSession = Depends(get_db),
):
    scenario_id = body.scenario_id

    # If no scenario_id but custom params provided — pick a fallback scenario
    if scenario_id is None and body.custom_archetype:
        # Pick first active scenario as base (CharacterBuilder overrides character behavior)
        result = await db.execute(
            select(Scenario).where(Scenario.is_active.is_(True)).limit(1)
        )
        fallback = result.scalar_one_or_none()
        if fallback is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err.NO_ACTIVE_SCENARIOS,
            )
        scenario_id = fallback.id
    elif scenario_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scenario_id or custom_archetype is required",
        )

    # Build custom_params dict if any custom fields provided (skip JSON null sent as string)
    custom_params = None
    arch = body.custom_archetype
    if arch and (not isinstance(arch, str) or arch.strip().lower() not in ("", "null")):
        raw = {
            "archetype": arch,
            "profession": body.custom_profession,
            "lead_source": body.custom_lead_source,
            "difficulty": body.custom_difficulty,
        }
        custom_params = {
            k: v
            for k, v in raw.items()
            if v is not None and (not isinstance(v, str) or v.strip().lower() not in ("", "null"))
        }
        if not custom_params:
            custom_params = None

    # Check rate limit before creating session
    try:
        await sm_check_rate_limit(user.id, db)
    except SmRateLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    session = TrainingSession(
        user_id=user.id,
        scenario_id=scenario_id,
        custom_params=custom_params,
    )
    db.add(session)
    await db.flush()

    # Initialize Redis state and emotion (mirrors session_manager.start_session)
    try:
        from app.models.character import EmotionState
        await sm_init_emotion(session.id, EmotionState.cold)
    except Exception:
        logger.warning("Failed to init emotion for session %s via REST", session.id)

    try:
        import json as _json
        import time as _time
        from app.services.session_manager import _redis, _SESSION_KEY, _KEY_TTL
        r = _redis()
        state_key = _SESSION_KEY.format(session_id=session.id)
        redis_state = {
            "user_id": str(user.id),
            "scenario_id": str(scenario_id),
            "status": "active",
            "started_at": _time.time(),
            "message_count": 0,
            "last_activity": _time.time(),
        }
        await r.set(state_key, _json.dumps(redis_state), ex=_KEY_TTL)
    except Exception:
        logger.warning("Failed to init Redis state for session %s via REST", session.id)

    return session


@router.get("/sessions/{session_id}", response_model=SessionResultResponse)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.SESSION_NOT_FOUND)
    return await _build_session_result(session, user=user, db=db)


@router.post("/sessions/{session_id}/end", response_model=SessionResponse)
async def end_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == user.id,
            TrainingSession.status == SessionStatus.active,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.ACTIVE_SESSION_NOT_FOUND)

    # Calculate scores before closing
    scores = None
    try:
        scores = await calculate_scores(session_id, db)
        session.score_script_adherence = scores.script_adherence
        session.score_objection_handling = scores.objection_handling
        session.score_communication = scores.communication
        session.score_anti_patterns = scores.anti_patterns
        session.score_result = scores.result
        session.score_total = scores.total

        # Enrich scoring_details with Wave 2 metadata
        enriched = dict(scores.details) if scores.details else {}
        try:
            from app.models.roleplay import ClientProfile
            from app.services.client_generator import get_full_reveal_card
            cp_result = await db.execute(
                select(ClientProfile).where(ClientProfile.session_id == session_id)
            )
            cp = cp_result.scalar_one_or_none()
            if cp:
                enriched["_client_name"] = cp.full_name
                enriched["_client_card_reveal"] = get_full_reveal_card(cp)
        except Exception:
            logger.debug("Failed to enrich with client reveal data for %s", session_id)

        session.scoring_details = enriched
    except Exception:
        logger.exception("Failed to calculate scores for session %s", session_id)

    # Generate AI recommendations
    try:
        recommendations = await generate_recommendations(session_id, db, scores)
        session.feedback_text = recommendations
    except Exception:
        logger.exception("Failed to generate recommendations for session %s", session_id)

    # Finalize via session_manager (duration, emotion timeline, Redis cleanup)
    try:
        await sm_end_session(session_id, db, status=SessionStatus.completed)
    except Exception:
        logger.warning("Failed to end session via manager for %s", session_id)
        # Fallback: set status manually if session_manager failed
        session.status = SessionStatus.completed
        await db.flush()

    # Award achievements after session completion
    try:
        await check_and_award_achievements(user.id, db)
    except Exception:
        logger.exception("Failed to check achievements for user %s", user.id)

    return session


@router.get("/recommended")
async def get_recommended(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    count: int = 3,
):
    """Get adaptive scenario recommendations based on performance.

    Uses difficulty engine to analyze recent scores and suggest optimal next scenarios.
    Considers: performance band, archetype rotation, staleness, untrained archetypes.
    """
    from app.services.difficulty import get_difficulty_profile, get_recommended_scenarios

    profile = await get_difficulty_profile(user.id, db)
    scenarios = await get_recommended_scenarios(user.id, db, count=count)

    return {
        "profile": {
            "current_level": profile.current_level,
            "target_level": profile.target_level,
            "avg_score": profile.avg_score,
            "sessions_analyzed": profile.sessions_analyzed,
            "trend": profile.trend,
            "band": profile.band,
        },
        "scenarios": [
            {
                "scenario_id": str(s.scenario_id),
                "title": s.title,
                "description": s.description,
                "scenario_type": s.scenario_type,
                "difficulty": s.difficulty,
                "archetype_slug": s.archetype_slug,
                "archetype_name": s.archetype_name,
                "reason": s.reason,
                "priority": s.priority,
                "tags": s.tags,
            }
            for s in scenarios
        ],
    }


@router.get("/history", response_model=list[HistoryEntryResponse])
async def training_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 20,
    offset: int = 0,
):
    sessions_result = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.user_id == user.id)
        .order_by(TrainingSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    recent_sessions = list(sessions_result.scalars().all())

    story_ids = {s.client_story_id for s in recent_sessions if s.client_story_id is not None}
    story_map: dict[uuid.UUID, ClientStory] = {}
    story_sessions_map: dict[uuid.UUID, list[TrainingSession]] = defaultdict(list)

    if story_ids:
        stories_result = await db.execute(
            select(ClientStory)
            .where(
                ClientStory.id.in_(story_ids),
                ClientStory.user_id == user.id,
            )
        )
        stories = list(stories_result.scalars().all())
        story_map = {story.id: story for story in stories}

        story_sessions_result = await db.execute(
            select(TrainingSession)
            .where(
                TrainingSession.user_id == user.id,
                TrainingSession.client_story_id.in_(story_ids),
            )
            .order_by(TrainingSession.call_number_in_story.asc(), TrainingSession.started_at.asc())
        )
        for story_session in story_sessions_result.scalars().all():
            if story_session.client_story_id is not None:
                story_sessions_map[story_session.client_story_id].append(story_session)

    items: list[HistoryEntryResponse] = []
    seen_story_ids: set[uuid.UUID] = set()

    for session in recent_sessions:
        if session.client_story_id and session.client_story_id in story_map:
            story_id = session.client_story_id
            if story_id in seen_story_ids:
                continue
            seen_story_ids.add(story_id)

            story = story_map[story_id]
            story_sessions = story_sessions_map.get(story_id, [])
            story_summary = _story_to_summary(story, story_sessions)
            latest_session = max(story_sessions, key=lambda s: s.started_at) if story_sessions else session
            story_calls = [_story_call_summary(s) for s in story_sessions]

            items.append(
                HistoryEntryResponse(
                    kind="story",
                    sort_at=latest_session.started_at,
                    latest_session=_session_to_response(latest_session),
                    story=story_summary,
                    sessions=story_calls,
                    calls_completed=story_summary.completed_calls,
                    avg_score=story_summary.avg_score,
                    best_score=story_summary.best_score,
                )
            )
            continue

        score = session.score_total
        items.append(
            HistoryEntryResponse(
                kind="session",
                sort_at=session.started_at,
                latest_session=_session_to_response(session),
                story=None,
                sessions=[_story_call_summary(session)],
                calls_completed=1,
                avg_score=score,
                best_score=score,
            )
        )

    items.sort(key=lambda item: item.sort_at, reverse=True)
    return items


# ─── Assignment endpoints ────────────────────────────────────────────────────


class AssignTrainingRequest(BaseModel):
    user_id: uuid.UUID
    scenario_id: uuid.UUID
    deadline: str | None = Field(None, description="ISO datetime or null")

    @field_validator("deadline")
    @classmethod
    def validate_deadline_iso(cls, v: str | None) -> str | None:
        if v is None:
            return None
        from datetime import datetime
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(err.DEADLINE_FORMAT_ERROR)
        return v


class AssignedTrainingResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    scenario_id: uuid.UUID
    assigned_by: uuid.UUID
    deadline: str | None = None
    completed_at: str | None = None
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/assign", status_code=status.HTTP_201_CREATED)
async def assign_training(
    body: AssignTrainingRequest,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """ROP/admin assigns a training scenario to a manager."""
    from datetime import datetime

    # Verify target user exists
    target = await db.execute(select(User).where(User.id == body.user_id))
    if target.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.TARGET_USER_NOT_FOUND)

    assignment = AssignedTraining(
        user_id=body.user_id,
        scenario_id=body.scenario_id,
        assigned_by=user.id,
        deadline=datetime.fromisoformat(body.deadline) if body.deadline else None,
    )
    db.add(assignment)
    await db.flush()

    return {"id": str(assignment.id), "message": err.TRAINING_ASSIGNED}


@router.get("/assigned")
async def get_my_assignments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get training assignments for the current user."""
    from app.models.scenario import Scenario

    result = await db.execute(
        select(AssignedTraining, Scenario.title)
        .join(Scenario, Scenario.id == AssignedTraining.scenario_id)
        .where(
            AssignedTraining.user_id == user.id,
            AssignedTraining.completed_at.is_(None),
        )
        .order_by(AssignedTraining.created_at.desc())
    )
    rows = result.all()

    return [
        {
            "id": str(row[0].id),
            "scenario_id": str(row[0].scenario_id),
            "scenario_title": row[1],
            "assigned_by": str(row[0].assigned_by),
            "deadline": row[0].deadline.isoformat() if row[0].deadline else None,
            "created_at": row[0].created_at.isoformat(),
        }
        for row in rows
    ]
