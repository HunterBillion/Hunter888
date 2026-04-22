import logging
import uuid
from collections import defaultdict

from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.consent import check_consent_accepted
from app.core import errors as err
from app.core.deps import get_current_user
from app.database import get_db
from app.core.deps import require_role
from app.models.client import ClientInteraction, InteractionType, RealClient
from app.models.roleplay import ClientStory
from app.models.training import AssignedTraining, Message, MessageRole, SessionStatus, TrainingSession
from app.models.scenario import Scenario, ScenarioTemplate, ScenarioType
from app.models.user import User
from pydantic import BaseModel, Field, field_validator
from app.schemas.training import (
    HistoryEntryResponse,
    IdealResponseResult,
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
                status=t.get("status"),
                client_phrase=t.get("client_phrase") or None,
                correct_example=t.get("correct_example") or None,
                explanation=t.get("explanation") or None,
                law_reference=t.get("law_reference") or None,
                correct_keywords=t.get("correct_keywords") or None,
                wrong_keywords=t.get("wrong_keywords") or None,
                category=t.get("category") or None,
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

    # ── 3.1: Extract weak legal categories from L10 for Knowledge Quiz link ──
    weak_legal: list | None = None
    legal_details = details.get("legal_accuracy", {})
    legal_score = legal_details.get("combined_score", 0)
    if legal_score is not None and legal_score < 2.5:
        from app.schemas.training import WeakLegalCategory
        _LEGAL_CATEGORY_MAP = {
            "eligibility": "Условия подачи",
            "procedure": "Процедура",
            "property": "Имущество",
            "consequences": "Последствия",
            "costs": "Стоимость",
            "creditors": "Кредиторы",
            "documents": "Документы",
            "timeline": "Сроки",
            "court": "Суд",
            "rights": "Права",
        }
        seen_cats: set[str] = set()
        weak_items: list[WeakLegalCategory] = []

        # From regex details: extract article references and categories
        regex_checks = legal_details.get("regex", {}).get("details", [])
        for check in regex_checks[:20]:  # Limit processing
            cat = check.get("category", "")
            if cat and cat not in seen_cats:
                seen_cats.add(cat)
                weak_items.append(WeakLegalCategory(
                    category=cat,
                    display_name=_LEGAL_CATEGORY_MAP.get(cat, cat),
                    accuracy_pct=max(0, min(100, int((legal_score + 5) / 10 * 100))),
                    article_refs=[
                        ref for ref in [check.get("law_article", "")]
                        if ref and len(ref) < 100
                    ],
                ))

        # From vector checks: extract fact references
        vector_checks = legal_details.get("vector", {}).get("vector_checks", [])
        for vc in vector_checks[:10]:
            if vc.get("type") == "error":
                fact = vc.get("fact", "")[:80]
                if fact and "general" not in seen_cats:
                    seen_cats.add("general")
                    weak_items.append(WeakLegalCategory(
                        category="general",
                        display_name="Общие знания ФЗ-127",
                        accuracy_pct=max(0, min(100, int((legal_score + 5) / 10 * 100))),
                        article_refs=[],
                    ))

        if weak_items:
            weak_legal = weak_items[:5]  # Max 5 categories

    # ── 3.2: Extract promise fulfillment from CRM story memory ──
    promise_data: list | None = None
    if session.client_story_id:
        from app.schemas.training import PromiseFulfillment
        promises_raw = details.get("_promises", [])
        if promises_raw:
            promise_data = [
                PromiseFulfillment(
                    text=str(p.get("text", ""))[:200],
                    call_number=int(p.get("call_number", 1)),
                    fulfilled=bool(p.get("fulfilled", False)),
                    impact="bonus" if p.get("fulfilled") else "penalty",
                )
                for p in promises_raw[:10]
                if p.get("text")
            ]

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
        weak_legal_categories=weak_legal,
        promise_fulfillment=promise_data,
    )


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
# 60/minute = 1 per second. Legit users never hit this; protects against
# runaway client loops and scripted abuse while staying out of the way
# during normal flow (multiple scenario clicks, start/end cycles, etc.).
# Bumped from 10/minute (2026-04-21) — old cap locked users out after a
# handful of failed calls during the call-mode bug investigation.
@limiter.limit("60/minute")
async def start_session(
    request: Request,
    body: SessionStartRequest,
    user: User = Depends(check_consent_accepted),
    db: AsyncSession = Depends(get_db),
):
    # ── 2026-04-23 Zone 4 — clone_from_session_id expansion ──────────────
    # When the user clicks «Повторить сценарий» on /results, frontend sends
    # ONLY `clone_from_session_id`. Backend copies scenario_id, real_client_id,
    # custom_character_id, custom_params, session_mode from the source session
    # into the request body. Explicit body fields win (clone is a template,
    # not a hard override) — this lets the user «retrain with different
    # difficulty» by sending clone_from_session_id + custom_difficulty=8.
    #
    # NOTE: this runs BEFORE scenario fallback / validation so all downstream
    # logic sees a fully-populated request, as if the user had sent everything
    # manually.
    _clone_source_id: "uuid.UUID | None" = None
    if body.clone_from_session_id:
        _clone_source = (await db.execute(
            select(TrainingSession).where(
                TrainingSession.id == body.clone_from_session_id,
                TrainingSession.user_id == user.id,  # own sessions only
            )
        )).scalar_one_or_none()
        if _clone_source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="clone_source_session_not_found",
            )
        _clone_source_id = _clone_source.id
        _src_cp = _clone_source.custom_params or {}

        # Scalar fields — explicit body value wins, clone fills absent.
        if body.scenario_id is None:
            body.scenario_id = _clone_source.scenario_id
        if body.real_client_id is None:
            body.real_client_id = _clone_source.real_client_id
        if body.custom_character_id is None:
            body.custom_character_id = _clone_source.custom_character_id

        # Flat custom_* fields — copy from source custom_params if body empty.
        # Note: schema flattens these into body.custom_* and start_session
        # re-serialises back into custom_params JSON below. We inject here.
        _CLONE_CP_KEYS = (
            ("custom_archetype",        "archetype"),
            ("custom_profession",       "profession"),
            ("custom_lead_source",      "lead_source"),
            ("custom_difficulty",       "difficulty"),
            ("custom_family_preset",    "family_preset"),
            ("custom_creditors_preset", "creditors_preset"),
            ("custom_debt_stage",       "debt_stage"),
            ("custom_debt_range",       "debt_range"),
            ("custom_emotion_preset",   "emotion_preset"),
            ("custom_bg_noise",         "bg_noise"),
            ("custom_time_of_day",      "time_of_day"),
            ("custom_fatigue",          "client_fatigue"),
            ("custom_session_mode",     "session_mode"),
            ("custom_tone",             "tone"),
        )
        for body_attr, cp_key in _CLONE_CP_KEYS:
            if getattr(body, body_attr, None) is None and cp_key in _src_cp:
                setattr(body, body_attr, _src_cp[cp_key])

        # Diagnostic source stamp (truncated hex for brevity in logs).
        if not body.source:
            body.source = f"retrain_from_{_clone_source.id.hex[:8]}"

        logger.info(
            "clone_from_session_id resolved | user=%s | source=%s | mode=%s "
            "| real_client_id=%s | custom_character_id=%s",
            user.id, _clone_source.id,
            body.custom_session_mode, body.real_client_id, body.custom_character_id,
        )

    # ── 2026-04-23 Zone 1 — real_client_id ownership validation ───────────
    # Frontend /clients/[id]/page.tsx sends real_client_id + source on both
    # "Написать" and "Позвонить". Without this check, a malicious user could
    # clone another manager's CRM card into their own training by forging
    # the request body. manager_id check catches it at schema-level.
    if body.real_client_id:
        _rc = (await db.execute(
            select(RealClient).where(
                RealClient.id == body.real_client_id,
                RealClient.manager_id == user.id,
            )
        )).scalar_one_or_none()
        if _rc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="real_client_not_found",
            )
        # real_client passed — scenario becomes optional (we have a client
        # profile source). Fall-back scenario picker below still runs if
        # nothing provided.

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
    # 2026-04-21: expanded from 4 fields to 11. Previously only archetype /
    # profession / lead_source / difficulty were persisted — the 7 extended
    # fields from the constructor (emotion_preset, family/creditors/debt,
    # bg_noise, time_of_day, fatigue) were accepted by the schema but never
    # actually stored, so Steps 3/4/6 of the constructor silently did
    # nothing. Now all 11 fields reach custom_params and downstream
    # generators. Sentinel values like "neutral", "afternoon", "normal" are
    # NOT filtered out — those are valid user choices, not pseudo-defaults.
    # Only real emptiness (None / "" / "null") is dropped.
    custom_params = None
    arch = body.custom_archetype
    if arch and (not isinstance(arch, str) or arch.strip().lower() not in ("", "null")):
        raw = {
            "archetype": arch,
            "profession": body.custom_profession,
            "lead_source": body.custom_lead_source,
            "difficulty": body.custom_difficulty,
            # Step 3: client context
            "family_preset": body.custom_family_preset,
            "creditors_preset": body.custom_creditors_preset,
            "debt_stage": body.custom_debt_stage,
            "debt_range": body.custom_debt_range,
            # Step 4: emotional preset + tone (2026-04-22: tone was accepted by
            # schema and read downstream in ws/training.py but never written to
            # custom_params here — constructor's Tone selector was silently
            # ignored on the REST path. Story-mode URL path already worked.)
            "emotion_preset": body.custom_emotion_preset,
            "tone": body.custom_tone,
            # Step 6: environment
            "bg_noise": body.custom_bg_noise,
            "time_of_day": body.custom_time_of_day,
            "client_fatigue": body.custom_fatigue,
        }
        custom_params = {
            k: v
            for k, v in raw.items()
            if v is not None and (not isinstance(v, str) or v.strip().lower() not in ("", "null"))
        }
        if not custom_params:
            custom_params = None

    # Session mode — "chat" (default) or "call". Persist so WS handlers +
    # LLM prompt builder can adapt behavior (call mode → phone-like short
    # replies, chat mode → normal text conversation).
    if body.custom_session_mode in ("chat", "call"):
        custom_params = custom_params or {}
        custom_params["session_mode"] = body.custom_session_mode

    # Validate that scenario exists and is active.
    # Check both legacy `scenarios` table and new `scenario_templates` table
    # because list_scenarios now returns template IDs.
    scenario_check = await db.execute(
        select(Scenario).where(Scenario.id == scenario_id, Scenario.is_active.is_(True))
    )
    if scenario_check.scalar_one_or_none() is None:
        # Not in legacy table — check scenario_templates and auto-create a
        # Scenario row so existing session logic works unchanged.
        tpl_check = await db.execute(
            select(ScenarioTemplate).where(
                ScenarioTemplate.id == scenario_id, ScenarioTemplate.is_active.is_(True)
            )
        )
        tpl = tpl_check.scalar_one_or_none()
        if tpl is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=err.SCENARIO_NOT_FOUND,
            )
        # Map template code prefix to legacy ScenarioType for FK compat
        code = tpl.code or ""
        if code.startswith("cold"):
            legacy_type = ScenarioType.cold_call
        elif code.startswith("warm"):
            legacy_type = ScenarioType.warm_call
        elif code.startswith("in_"):
            legacy_type = ScenarioType.consultation
        else:
            legacy_type = ScenarioType.objection_handling
        # Find a default character for the FK (pick first active character)
        from app.models.character import Character
        char_result = await db.execute(select(Character.id).limit(1))
        default_char_id = char_result.scalar_one_or_none()
        if default_char_id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No characters in database",
            )
        # Auto-create a Scenario row linked to this template
        new_scenario = Scenario(
            id=tpl.id,  # reuse template UUID so session references it
            title=tpl.name,
            description=tpl.description,
            scenario_type=legacy_type,
            character_id=default_char_id,
            template_id=tpl.id,
            difficulty=tpl.difficulty,
            estimated_duration_minutes=tpl.typical_duration_minutes,
        )
        db.add(new_scenario)
        await db.flush()

    # ── FIND-001 (2026-04-19): Idempotency-Key replay BEFORE rate-limit.
    # Retrying with the same key must NOT consume fresh quota — that would
    # punish well-behaved clients that retry idempotently on flaky networks.
    # So we check the idempotency cache first; only misses continue to the
    # rate limiter + creation path below.
    import json as _idem_json

    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        try:
            from app.core.redis_pool import get_redis as _idem_get_redis_early
            _r_early = _idem_get_redis_early()
            _ik_key_early = f"idem:session:{user.id}:{idempotency_key}"
            cached = await _r_early.get(_ik_key_early)
            if cached:
                payload = _idem_json.loads(cached)
                logger.info(
                    "idempotency replay user=%s key=%s session=%s",
                    user.id, idempotency_key, payload.get("id"),
                )
                return SessionResponse(**payload)
        except Exception:
            logger.debug("idempotency read failed", exc_info=True)

    # Check rate limit before creating session
    try:
        await sm_check_rate_limit(user.id, db)
    except SmRateLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e))

    # ── FIND-001 (2026-04-19): idempotency + active-session dedup ──────────
    # Three layers of protection against duplicate session creation:
    #
    # (1) Idempotency-Key header replay. Standard HTTP pattern: client
    #     sends the same ``Idempotency-Key`` on retries, server caches
    #     the response for 5 minutes under ``idem:session:{user}:{key}``
    #     and returns the same session on dup. Makes retries on flaky
    #     networks safe. NOTE: reliable only for sequential retries — for
    #     concurrent bursts the Redis SETNX below is what actually
    #     serialises.
    #
    # (2) Redis SETNX per-user creation lock. Atomic claim under
    #     ``lock:create_session:{user_id}`` with a 5-second TTL.  If we
    #     can't grab it, another parallel request is creating right now
    #     — we reject 409 instead of racing. Fail-open on Redis errors
    #     (production nginx rate-limits already bound the blast radius).
    #
    # (3) Active-session deduplication. Even without a key or Redis, if
    #     the same user already has an active session opened in the last
    #     60 seconds (e.g. from a different client or after the lock
    #     TTL), reject with 409 + existing session id. Frontend can
    #     resume or explicitly close+retry.
    # (Idempotency-Key read above before the rate-limit check — cache hit
    # short-circuits the whole path. The Redis lock and active-session
    # guards below still run for cache misses.)
    _LOCK_TTL_S = 5

    # SETNX per-user creation lock (atomic, protects against concurrent
    # creation bursts that the DB-level duplicate check can't serialise).
    _lock_acquired = False
    try:
        from app.core.redis_pool import get_redis as _get_redis

        _lock_key = f"lock:create_session:{user.id}"
        _r_lock = _get_redis()
        # SET NX EX — atomic acquire with TTL. Returns True iff we got it.
        _lock_acquired = bool(
            await _r_lock.set(_lock_key, "1", nx=True, ex=_LOCK_TTL_S)
        )
        if not _lock_acquired:
            logger.info(
                "create_session lock busy user=%s — concurrent create", user.id,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "session_create_in_progress",
                    "message": (
                        "Другой запрос на создание сессии обрабатывается "
                        "прямо сейчас. Подожди секунду и попробуй снова."
                    ),
                },
            )
    except HTTPException:
        raise
    except Exception:
        logger.debug("SETNX lock failed; falling through", exc_info=True)

    try:
        # Phase F (2026-04-20) — two-tier handling of existing active
        # sessions. Owner feedback: «зашёл только что, а мне говорят
        # у тебя уже сессия!». Forensics: в БД висели зомби-сессии
        # возрастом 1-40 часов (abandoned без явного close).
        #
        # Tier 1: **auto-abandon stale** (> 5 min). Юзер явно ушёл,
        # вернулся через какое-то время → его зомби-сессия больше не
        # блокирует новую. Marked as `abandoned` (not `completed`)
        # чтобы аналитика видела что сессия была брошена.
        #
        # Tier 2: **block recent** (< 15s). Это защита от реального
        # double-click / race — юзер клинул дважды, не хотим создать
        # две сессии под один клик. Окно уменьшено с 60 → 15 сек, т.к.
        # 60 был слишком агрессивным (юзер успевал забыть и повторно
        # кликал, застревал).
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        # 2026-04-21 TZ FIX (journal #16): previously used _dt.utcnow() (naive).
        # TrainingSession.started_at is TIMESTAMP WITH TIME ZONE, so comparing
        # a naive utcnow() against a tz-aware column either raised in Postgres
        # or silently coerced using server-local time — both wrong. The except
        # block below swallowed the resulting exception at logger.debug, so
        # stale sessions were NEVER abandoned in prod, users saw phantom 409s
        # indefinitely. Now everything is tz-aware UTC end to end, and failures
        # are escalated to warning so they are visible in production logs.
        _now = _dt.now(_tz.utc)
        # 2026-04-21: tightened from 5 min to 1 min. A real training session
        # rarely sits idle >1 min without activity; old 5-min window left
        # users stuck in a 409 deadzone when they closed the tab and reopened
        # shortly after. Mode-switch abandon (below) handles chat↔call swaps
        # independently.
        try:
            _stale_q = await db.execute(
                select(TrainingSession)
                .where(TrainingSession.user_id == user.id)
                .where(TrainingSession.status == SessionStatus.active)
                .where(TrainingSession.started_at <= _now - _td(minutes=1))
            )
            _stale_rows = list(_stale_q.scalars())
            if _stale_rows:
                for _s in _stale_rows:
                    _s.status = SessionStatus.abandoned
                    _s.ended_at = _now
                await db.flush()
                logger.info(
                    "Auto-abandoned %d stale active sessions for user=%s",
                    len(_stale_rows), user.id,
                )
        except Exception:
            # Visible in prod. Stale-abandon failure means the user can't start
            # a new session until manual DB cleanup — not acceptable to hide.
            logger.warning("stale session auto-abandon failed", exc_info=True)

        # Tier 2 — block recent double-click (window 15s).
        # Mode-aware: if the existing active session is in a DIFFERENT
        # session_mode than the one being requested (chat ↔ call), the user
        # is deliberately switching modes — auto-abandon the old one and let
        # the new POST through. Otherwise a pending chat session would hijack
        # a fresh call request (the user clicks "звонок" but lands in chat UI
        # via existing_session_id redirect).
        _requested_mode = None
        if body.custom_session_mode in ("chat", "call"):
            _requested_mode = body.custom_session_mode
        try:
            _dup_q = await db.execute(
                select(TrainingSession.id, TrainingSession.custom_params)
                .where(TrainingSession.user_id == user.id)
                .where(TrainingSession.status == SessionStatus.active)
                .where(TrainingSession.started_at > _now - _td(seconds=15))
                .order_by(TrainingSession.started_at.desc())
                .limit(1)
            )
            _dup_row = _dup_q.first()
            _dup_id = _dup_row[0] if _dup_row else None
            _dup_cp = _dup_row[1] if _dup_row else None
        except Exception:
            # Raised to warning (journal #16 class C). This check is a state
            # invariant — if it silently fails, users can race two sessions.
            logger.warning("duplicate-active check failed", exc_info=True)
            _dup_id = None
            _dup_cp = None

        if _dup_id is not None:
            _existing_mode = (_dup_cp or {}).get("session_mode") or "chat"
            # Mode mismatch → user is switching modes. Abandon the stale one.
            if _requested_mode and _requested_mode != _existing_mode:
                try:
                    await db.execute(
                        update(TrainingSession)
                        .where(TrainingSession.id == _dup_id)
                        .values(status=SessionStatus.abandoned, ended_at=_now)
                    )
                    await db.flush()
                    logger.info(
                        "Mode switch abandon | user=%s | old=%s (%s) → new=%s",
                        user.id, _dup_id, _existing_mode, _requested_mode,
                    )
                except Exception:
                    # journal #16 class C: user presses «Звонок» on existing
                    # chat session, this should switch. Silent failure means
                    # user gets bounced to old chat mode and never lands in
                    # call UI — exactly the «выкинуло в чат» symptom.
                    logger.warning("mode-switch abandon failed", exc_info=True)
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "session_already_active",
                        "message": (
                            "У пользователя уже есть активная тренировка, "
                            "начатая несколько секунд назад. Открываю её."
                        ),
                        "existing_session_id": str(_dup_id),
                    },
                )
    except HTTPException:
        # Release lock on known errors so next attempt isn't blocked for TTL.
        if _lock_acquired:
            try:
                await _r_lock.delete(_lock_key)
            except Exception:
                pass
        raise

    # 2026-04-21: persist the CustomCharacter FK so end_session can
    # increment play_count/best_score/avg_score/last_played_at later. The
    # column has existed since migration 20260404_006 but nothing on the
    # write side filled it — it stayed NULL for every session, making the
    # saved-characters statistics permanently dead.
    session = TrainingSession(
        user_id=user.id,
        scenario_id=scenario_id,
        custom_params=custom_params,
        custom_character_id=body.custom_character_id,
        # 2026-04-23 Zone 1: persist CRM-card linkage so WS handler builds
        # the ClientProfile from RealClient instead of random generation.
        real_client_id=body.real_client_id,
        # 2026-04-23 Zone 4: retrain lineage — who did this session clone.
        source_session_id=_clone_source_id,
        # 2026-04-23: persist diagnostic source stamp (crm_chat / crm_voice /
        # retrain_from_xxx / constructor_* / None). Column existed but
        # nothing wrote to it before.
        source=body.source,
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

    # FIND-001 (2026-04-19): cache the final response under the
    # Idempotency-Key for 5 minutes so retries return the same session id
    # instead of creating a new row. Best-effort — Redis hiccup doesn't
    # break the request.
    if idempotency_key:
        try:
            from app.core.redis_pool import get_redis as _idem_get_redis
            _r2 = _idem_get_redis()
            _ik_key = f"idem:session:{user.id}:{idempotency_key}"
            _resp = SessionResponse.model_validate(session).model_dump(
                mode="json"
            )
            await _r2.setex(_ik_key, 300, _idem_json.dumps(_resp, default=str))
        except Exception:
            logger.debug("idempotency write failed", exc_info=True)

    # Release the create-session lock — a subsequent POST from the same
    # user can proceed immediately (it still trips the active-session
    # guard above until this one ends).
    if _lock_acquired:
        try:
            await _r_lock.delete(_lock_key)
        except Exception:
            pass

    return session


@router.post("/sessions/{session_id}/script-hints")
@limiter.limit("30/minute")
async def generate_script_hints(
    session_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate 3 LLM-powered reply suggestions tailored to the current call state.

    Called by the client whenever it wants hints (start of call, after each
    client message, or on demand via the coaching-panel toggle).

    Returns: { hints: [{text: str, label: str}] }
    """
    from app.services.llm import generate_response
    from app.models.training import TrainingSession, Message, MessageRole
    from sqlalchemy import select as _select

    # Verify ownership
    ses_q = await db.execute(
        _select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == user.id,
        )
    )
    session = ses_q.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err.SESSION_NOT_FOUND)

    # Fetch the last 6 messages for context
    msg_q = await db.execute(
        _select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number.desc())
        .limit(6)
    )
    recent = list(reversed(msg_q.scalars().all()))
    history_text = "\n".join(
        f"{'Менеджер' if m.role == MessageRole.user else 'Клиент'}: {m.content}"
        for m in recent
    ) or "(звонок ещё не начался)"

    # Load scenario title for context
    from app.models.scenario import Scenario
    scen_q = await db.execute(_select(Scenario).where(Scenario.id == session.scenario_id))
    scenario = scen_q.scalar_one_or_none()
    scenario_ctx = scenario.title if scenario else "Звонок клиенту-должнику"

    # 2026-04-21: hints used to be archetype-agnostic — same three templates
    # ("empathy / structure / question") regardless of whether the client
    # was harsh or friendly. For constructor-built clients this was jarring:
    # a friendly client got the same hard-sell hints as a hostile one. Now
    # the builder's archetype + tone + emotion preset flow into the coach's
    # system prompt so suggestions match the actual client. Legacy scenarios
    # without custom_params get the old generic behaviour.
    _cp = session.custom_params or {}
    _arch = _cp.get("archetype")
    _tone = _cp.get("tone")
    _emotion = _cp.get("emotion_preset")
    _TONE_HINT = {
        "harsh": "клиент жёсткий — предлагай короткие, прямые формулировки без лишней вежливости",
        "friendly": "клиент дружелюбный — предлагай тёплые, персональные формулировки, не давящие",
        "lively": "клиент живой/эмоциональный — подсказки могут быть игривее, ловить его настроение",
        "neutral": "клиент нейтральный — стандартный деловой стиль",
    }
    _EMOTION_HINT = {
        "anxious": "клиент тревожен — предлагай успокаивающие формулировки",
        "angry": "клиент раздражён — рапорт/эмпатия важнее структуры",
        "tired": "клиент устал — коротко и по делу, без давления",
        "rushed": "клиент спешит — давай самый ёмкий вариант первым",
        "hopeful": "клиент настроен с надеждой — подкрепляй это, не спугни",
        "trusting": "клиент открыт — можно глубже копать ситуацию",
    }
    _client_hints: list[str] = []
    if _arch:
        _client_hints.append(f"архетип={_arch}")
    if _tone and _tone in _TONE_HINT:
        _client_hints.append(_TONE_HINT[_tone])
    if _emotion and _emotion in _EMOTION_HINT:
        _client_hints.append(_EMOTION_HINT[_emotion])
    _client_block = (
        "\n\nКонтекст клиента для подсказок: " + "; ".join(_client_hints) + "."
        if _client_hints else ""
    )

    system_prompt = (
        "Ты — AI-коуч по продажам. Предложи 3 варианта следующей реплики менеджера. "
        "Каждая реплика должна быть РАЗНОЙ по стилю: "
        "(1) эмпатичная/рапортная, "
        "(2) деловая/структурная, "
        "(3) вопрос для раскрытия ситуации. "
        "КАЖДАЯ реплика — максимум 2 предложения, разговорная, готовая к отправке. "
        "Подсказки ДОЛЖНЫ соответствовать характеру и настроению клиента, если они указаны ниже. "
        "НЕ используй плейсхолдеры типа {имя}, напиши конкретно. "
        "Ответ СТРОГО в JSON формате: "
        '{"hints":[{"text":"...","label":"Эмпатия"},{"text":"...","label":"Структура"},{"text":"...","label":"Вопрос"}]}'
        + _client_block
    )
    user_prompt = f"Сценарий: {scenario_ctx}\n\nИстория:\n{history_text}\n\nДай 3 варианта следующей реплики менеджера."

    try:
        result = await generate_response(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            emotion_state="cold",
            task_type="coach",
            prefer_provider="auto",
        )
        import json
        raw = result.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        parsed = json.loads(raw)
        hints = parsed.get("hints", [])
        # Sanity filter
        hints = [h for h in hints if isinstance(h, dict) and h.get("text")]
        if not hints:
            raise ValueError("empty hints")
        return {"hints": hints[:4]}
    except Exception as e:
        logger.warning("Script hints LLM failed: %s", e)
        # Safe fallback — generic but better than nothing
        return {
            "hints": [
                {"text": "Понимаю, что ситуация непростая. Можете рассказать подробнее, с чего всё началось?", "label": "Эмпатия"},
                {"text": "Давайте разберём по порядку — какие у вас сейчас основные долги и перед кем?", "label": "Структура"},
                {"text": "А что для вас сейчас важнее — снизить ежемесячный платёж или вообще закрыть долги?", "label": "Вопрос"},
            ]
        }


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


@router.post("/sessions/{session_id}/decline", response_model=SessionResponse)
async def decline_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """2026-04-23 Zone 2 — user declined incoming call gate.

    Called from call/page.tsx IncomingCallScreen when user clicks
    "Отклонить" instead of "Принять". The session was already POSTed at
    /clients/[id]/page.tsx click (scenario_id + real_client_id), so the
    row exists in DB. We just mark it as abandoned without scoring and
    optionally log a ClientInteraction so the timeline shows the declined
    attempt.

    Idempotent: if session is already ended/abandoned, just return current
    state instead of erroring — user may double-click.
    """
    session = (await db.execute(
        select(TrainingSession).where(
            TrainingSession.id == session_id,
            TrainingSession.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=err.ACTIVE_SESSION_NOT_FOUND,
        )

    # Idempotent: don't modify terminal sessions.
    if session.status == SessionStatus.active:
        from datetime import datetime as _dt, timezone as _tz
        session.status = SessionStatus.abandoned
        session.ended_at = _dt.now(_tz.utc)
        # Log as CRM interaction if linked to real client (for timeline).
        if session.real_client_id:
            try:
                db.add(ClientInteraction(
                    client_id=session.real_client_id,
                    manager_id=user.id,
                    interaction_type=InteractionType.note,
                    notes=f"Отклонил входящий звонок (тренировка #{session.id.hex[:8]})",
                    metadata_={
                        "training_session_id": str(session.id),
                        "declined": True,
                        "session_mode": (session.custom_params or {}).get("session_mode"),
                    },
                ))
            except Exception:
                logger.warning(
                    "decline_session: ClientInteraction create failed for %s",
                    session.real_client_id, exc_info=True,
                )
        await db.commit()
        logger.info("Session %s declined by user %s", session.id, user.id)

    return SessionResponse.model_validate(session)


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

    # Retrieve emotion timeline from Redis BEFORE scoring (Wave 5 audit fix:
    # scoring layers L5, L8, L9 need the timeline for accurate computation)
    try:
        from app.services.emotion import get_emotion_timeline
        timeline_from_redis = await get_emotion_timeline(session_id)
        if timeline_from_redis:
            session.emotion_timeline = timeline_from_redis
            await db.flush()
    except Exception:
        logger.debug("Failed to pre-load emotion timeline for %s", session_id)

    # Calculate scores (now with populated emotion_timeline)
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

        # Wave 4: Enrich with layer explanations, skill radar, emotion journey
        try:
            from app.services.scoring import (
                generate_layer_explanations,
                layer_explanations_to_dict,
            )
            msg_result = await db.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at)
            )
            raw_msgs = msg_result.scalars().all()
            msg_dicts = [
                {"role": m.role.value if hasattr(m.role, "value") else str(m.role),
                 "content": m.content or "", "index": i}
                for i, m in enumerate(raw_msgs)
            ]
            explanations = generate_layer_explanations(scores, msg_dicts)
            enriched["_layer_explanations"] = layer_explanations_to_dict(explanations)
        except Exception:
            logger.debug("Failed to generate layer explanations for %s", session_id)

        # Skill radar (6-axis computed from L1-L10 weights)
        try:
            enriched["_skill_radar"] = scores.skill_radar
        except Exception:
            logger.debug("Failed to compute skill radar for %s", session_id)

        # Emotion journey summary (timeline + turning points)
        try:
            timeline = session.emotion_timeline or []
            if timeline:
                total_transitions = len(timeline)
                rollback_count = sum(1 for t in timeline if t.get("rollback"))
                fake_count = sum(1 for t in timeline if t.get("is_fake"))
                peak_order = ["cold", "skeptical", "guarded", "curious",
                              "considering", "warming", "open", "negotiating", "deal"]
                peak_idx = 0
                for t in timeline:
                    state = t.get("state", "cold")
                    if state in peak_order:
                        peak_idx = max(peak_idx, peak_order.index(state))
                turning_points = [
                    t for t in timeline
                    if t.get("rollback") or t.get("is_fake")
                       or t.get("state") in ("deal", "hangup", "hostile")
                ][:5]
                enriched["_emotion_journey"] = {
                    "summary": {
                        "total_transitions": total_transitions,
                        "rollback_count": rollback_count,
                        "peak_state": peak_order[peak_idx] if peak_idx < len(peak_order) else "cold",
                        "fake_count": fake_count,
                        "turning_points": turning_points,
                    },
                    "timeline": timeline,
                }
        except Exception:
            logger.debug("Failed to build emotion journey for %s", session_id)

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

    # 2026-04-21: reconcile CustomCharacter stats (play_count, best_score,
    # avg_score, last_played_at) when the session was linked to a saved
    # character. No-ops on sessions without a link. See
    # app/services/custom_character_stats.py for the full rationale.
    try:
        from app.services.custom_character_stats import update_custom_character_stats
        await update_custom_character_stats(session, db)
    except Exception:
        logger.warning("custom_character_stats update failed for %s", session_id, exc_info=True)

    # Emit event → EventBus handles achievements, goals, SRS seeding, notifications
    try:
        from app.services.event_bus import event_bus, GameEvent, EVENT_TRAINING_COMPLETED

        # Extract weak legal categories for SRS seeding
        event_payload: dict = {
            "session_id": str(session.id),
            "score": float(session.score_total) if session.score_total else 0.0,
        }
        if scores and scores.legal_accuracy < 0:
            details = session.scoring_details or {}
            legal_details = details.get("legal_accuracy", {})
            weak_cats = []
            regex_checks = legal_details.get("regex", {}).get("details", [])
            for check in regex_checks[:10]:
                cat = check.get("category", "")
                ref = check.get("law_article", "")
                if cat:
                    weak_cats.append({
                        "category": cat,
                        "display_name": cat,
                        "article_refs": [ref] if ref else [],
                    })
            if weak_cats:
                event_payload["weak_legal_categories"] = weak_cats[:5]

        # Journal: dedup by session_id so that when BOTH REST /end AND the
        # WS `session.end` handler complete the same training, we only emit
        # the event once (UNIQUE(idempotency_key) on OutboxEvent, second
        # INSERT is caught and skipped inside event_bus.emit).
        await event_bus.emit(
            GameEvent(
                kind=EVENT_TRAINING_COMPLETED,
                user_id=user.id,
                db=db,
                payload=event_payload,
            ),
            aggregate_id=session.id,
            idempotency_key=f"training_completed:{session.id}",
        )
    except Exception:
        logger.exception("EventBus failed for training_completed, user %s", user.id)

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

    # Load scenario title for notification
    scenario_result = await db.execute(select(Scenario).where(Scenario.id == body.scenario_id))
    scenario = scenario_result.scalar_one_or_none()
    scenario_title = scenario.title if scenario else "Тренировка"

    assignment = AssignedTraining(
        user_id=body.user_id,
        scenario_id=body.scenario_id,
        assigned_by=user.id,
        deadline=datetime.fromisoformat(body.deadline) if body.deadline else None,
    )
    db.add(assignment)
    await db.flush()

    # Send real-time notification to the assigned manager
    try:
        from app.ws.notifications import send_ws_notification
        deadline_str = body.deadline or "без дедлайна"
        await send_ws_notification(
            body.user_id,
            event_type="training.assigned",
            data={
                "assignment_id": str(assignment.id),
                "scenario_id": str(body.scenario_id),
                "scenario_title": scenario_title,
                "assigned_by": str(user.id),
                "assigned_by_name": user.full_name if hasattr(user, "full_name") else str(user.id),
                "deadline": deadline_str,
            },
        )
    except Exception:
        pass  # Notification failure should not block assignment

    await db.commit()

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


@router.get("/assigned/team")
async def get_team_assignments(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """ROP/admin: get all assignments for team members with completion status."""
    from app.models.scenario import Scenario
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(AssignedTraining, Scenario.title, User.email)
        .join(Scenario, Scenario.id == AssignedTraining.scenario_id)
        .join(User, User.id == AssignedTraining.user_id)
        .order_by(AssignedTraining.created_at.desc())
        .limit(100)
    )
    rows = result.all()

    assignments = []
    for row in rows:
        at = row[0]
        is_completed = at.completed_at is not None
        is_overdue = (
            not is_completed
            and at.deadline is not None
            and at.deadline < now
        )

        assignments.append({
            "id": str(at.id),
            "user_id": str(at.user_id),
            "user_email": row[2],
            "scenario_id": str(at.scenario_id),
            "scenario_title": row[1],
            "assigned_by": str(at.assigned_by),
            "deadline": at.deadline.isoformat() if at.deadline else None,
            "completed_at": at.completed_at.isoformat() if at.completed_at else None,
            "created_at": at.created_at.isoformat(),
            "status": "completed" if is_completed else ("overdue" if is_overdue else "pending"),
        })

    # Summary stats
    total = len(assignments)
    completed = sum(1 for a in assignments if a["status"] == "completed")
    overdue = sum(1 for a in assignments if a["status"] == "overdue")

    return {
        "assignments": assignments,
        "summary": {
            "total": total,
            "completed": completed,
            "pending": total - completed - overdue,
            "overdue": overdue,
        },
    }


# ── Recent home sessions (for /training Assigned tab) ─────────────────────


@router.get("/recent-home")
async def get_recent_home_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = 7,
):
    """Recent completed sessions started from /home (last N days).

    Used by the /training Assigned tab to show "Недавние" section.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(TrainingSession, Scenario.title)
        .join(Scenario, Scenario.id == TrainingSession.scenario_id)
        .where(
            TrainingSession.user_id == user.id,
            TrainingSession.source == "home",
            TrainingSession.status == SessionStatus.completed,
            TrainingSession.ended_at >= cutoff,
        )
        .order_by(TrainingSession.ended_at.desc())
        .limit(20)
    )
    rows = result.all()
    return [
        {
            "id": str(session.id),
            "scenario_id": str(session.scenario_id),
            "scenario_title": title,
            "score_total": session.score_total,
            "duration_seconds": session.duration_seconds,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "source": "home",
        }
        for session, title in rows
    ]


# ── AI-Coach: interactive post-session coaching chat ───────────────────────


class CoachQuestionRequest(BaseModel):
    question: str
    message_index: int | None = None  # Optional: reference to a specific message


@router.post("/sessions/{session_id}/coach")
@limiter.limit("5/minute")
async def ask_coach(
    request: Request,
    session_id: uuid.UUID,
    body: CoachQuestionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask AI-Coach a question about a completed training session.

    The coach analyzes the conversation and provides specific advice
    with citations from the actual dialogue.

    Only available for sessions with difficulty <= 6 (easy/medium).
    """
    from app.models.training import Message, MessageRole
    from app.services.llm import generate_response

    # Load session
    session = await db.get(TrainingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your session")

    # Check difficulty restriction (coach only for easy/medium)
    scenario_result = await db.execute(
        select(Scenario).where(Scenario.id == session.scenario_id)
    )
    scenario = scenario_result.scalar_one_or_none()
    difficulty = scenario.difficulty if scenario else 5
    if difficulty > 6:
        raise HTTPException(
            status_code=403,
            detail="AI-Coach доступен только для сценариев сложности 1-6. На сложных сценариях разбирайтесь самостоятельно!",
        )

    # Load conversation
    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    messages = msg_result.scalars().all()

    conversation_lines = []
    for i, m in enumerate(messages):
        role = "Менеджер" if m.role == MessageRole.user else "Клиент"
        conversation_lines.append(f"[{i}] {role}: {m.content}")
    conversation_text = "\n".join(conversation_lines)

    # Build context for the referenced message
    context_hint = ""
    if body.message_index is not None and 0 <= body.message_index < len(messages):
        ref_msg = messages[body.message_index]
        role = "менеджера" if ref_msg.role == MessageRole.user else "клиента"
        context_hint = f"\nМенеджер спрашивает про реплику [{body.message_index}] ({role}): \"{ref_msg.content[:200]}\"\n"

    # Build rich score context
    scoring_details = session.scoring_details or {}
    score_summary = f"Общий балл: {session.score_total or '?'}/100"

    # Stage progress context
    stage_ctx = ""
    stage_data = scoring_details.get("_stage_progress", {})
    if stage_data:
        completed = stage_data.get("stages_completed", [])
        stage_ctx = f"\nЭтапы скрипта: пройдено {len(completed)} из {stage_data.get('total_stages', 7)}. Финальный: {stage_data.get('final_stage_name', '?')}."

    # Skill radar context
    skill_ctx = ""
    skill_data = scoring_details.get("_skill_radar", {})
    if skill_data:
        skill_lines = [f"  {k}: {v:.0f}/100" for k, v in skill_data.items() if isinstance(v, (int, float))]
        if skill_lines:
            skill_ctx = "\nНавыки менеджера:\n" + "\n".join(skill_lines)

    # Cited moments from report (if available)
    cited_ctx = ""
    cited_moments = scoring_details.get("_cited_moments", [])
    if cited_moments:
        cited_lines = [f"  - Реплика [{cm.get('message_index')}]: {cm.get('problem', '')}" for cm in cited_moments[:3]]
        cited_ctx = "\nУже выявленные проблемы:\n" + "\n".join(cited_lines)

    coach_prompt = (
        "Ты — AI-тренер по продажам банкротства физических лиц (127-ФЗ). "
        "Менеджер прошёл тренировочную сессию и задаёт вопрос по разбору. "
        "Отвечай конкретно, ссылаясь на реплики из разговора по номерам [N]. "
        "Давай практичные советы — что конкретно сказать, как перефразировать. "
        "Приводи примеры фраз. Не повторяй то что уже было сказано.\n\n"
        f"Сценарий: {scenario.title if scenario else '?'} (сложность {difficulty}/10)\n"
        f"{score_summary}{stage_ctx}{skill_ctx}{cited_ctx}\n\n"
        f"Разговор:\n{conversation_text}\n\n"
        f"{context_hint}"
        f"Вопрос менеджера: {body.question}"
    )

    try:
        response = await generate_response(
            system_prompt=coach_prompt,
            messages=[{"role": "user", "content": body.question}],
            emotion_state="cold",
            user_id=f"coach:{user.id}",
            task_type="coach",
            prefer_provider="cloud",
        )
        answer = response.content
    except Exception as e:
        logger.error("Coach LLM failed: %s", e)
        answer = "К сожалению, AI-Coach временно недоступен. Попробуйте позже."

    # Find cited message indices in the answer
    import re
    cited = [int(m) for m in re.findall(r"\[(\d+)\]", answer) if int(m) < len(messages)]

    return {
        "answer": answer,
        "cited_messages": cited,
        "session_id": str(session_id),
    }


# ── Phase 2: AI Coach 2.0 ─────────────────────────────────────────────────────


class CoachChatRequest(BaseModel):
    message: str


@router.post("/coach/chat")
@limiter.limit("10/minute")
async def coach_chat_endpoint(
    request: Request,
    body: CoachChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Chat with AI Coach. Coach knows your patterns, techniques, and weak spots."""
    from app.services.ai_coach import coach_chat
    result = await coach_chat(user.id, body.message, db)
    return {
        "text": result.text,
        "action": result.action,
        "action_data": result.action_data,
    }


@router.get("/coach/tip")
async def coach_proactive_tip(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get proactive coaching tip based on current state."""
    from app.services.ai_coach import get_proactive_tip
    tip = await get_proactive_tip(user.id, db)
    return {"tip": tip}


# ── Phase 2: What-If Branching ────────────────────────────────────────────────


class WhatIfRequest(BaseModel):
    alternative_text: str


@router.post("/sessions/{session_id}/messages/{message_id}/what-if")
@limiter.limit("5/minute")
async def simulate_what_if(
    request: Request,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    body: WhatIfRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Simulate what would happen if the manager said something different.

    Takes a completed session + specific message + alternative text.
    Returns: AI client response to alternative, predicted emotion, score comparison.
    """
    from app.services.llm import generate_response

    session = await db.get(TrainingSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status != SessionStatus.completed:
        raise HTTPException(status_code=400, detail="Session must be completed")

    # Load messages up to target
    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    all_messages = msg_result.scalars().all()

    target_msg = None
    for m in all_messages:
        if m.id == message_id:
            target_msg = m
            break
    if not target_msg or target_msg.role != MessageRole.user:
        raise HTTPException(status_code=400, detail="Target must be a user message")

    # Build context up to target message
    history = []
    for m in all_messages:
        if m.sequence_number >= target_msg.sequence_number:
            break
        history.append({"role": m.role.value, "content": m.content})

    # Add alternative message
    history.append({"role": "user", "content": body.alternative_text})

    emotion_at_point = target_msg.emotion_state or "cold"

    # Get scenario for system prompt
    scenario = await db.get(Scenario, session.scenario_id) if session.scenario_id else None
    system_prompt = f"Ты — AI-клиент в тренировочной симуляции. Сценарий: {scenario.title if scenario else 'Тренировка'}. Текущая эмоция: {emotion_at_point}. Отвечай как клиент."

    try:
        client_response = await generate_response(
            system_prompt=system_prompt,
            messages=history,
            emotion_state=emotion_at_point,
            task_type="roleplay",
        )
    except Exception:
        raise HTTPException(status_code=500, detail="LLM generation failed")

    # Find original response (next message after target)
    original_response = None
    for m in all_messages:
        if m.sequence_number == target_msg.sequence_number + 1 and m.role == MessageRole.assistant:
            original_response = m
            break

    return {
        "alternative": {
            "manager_said": body.alternative_text,
            "client_would_say": client_response.content,
            "predicted_emotion": emotion_at_point,
        },
        "original": {
            "manager_said": target_msg.content,
            "client_said": original_response.content if original_response else None,
            "actual_emotion": original_response.emotion_state if original_response else None,
        },
    }


# ── Wave 5: Replay Mode — Ideal Response ─────────────────────────────────────


@router.post(
    "/sessions/{session_id}/messages/{message_id}/ideal-response",
    response_model=IdealResponseResult,
)
@limiter.limit("3/minute")
async def generate_ideal_response(
    request: Request,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate an ideal response for a specific manager message in a completed session.

    Replay Mode: Shows what the manager SHOULD have said at this point, with scoring
    comparison, emotion prediction, and trap handling analysis.

    Only available for completed sessions (user's own or admin/ROP with same team).
    """
    import re
    from app.models.training import Message, MessageRole
    from app.services.llm import generate_response

    # ── 1. Load & validate session ──
    session = await db.get(TrainingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # Ownership / team isolation check
    if session.user_id != user.id:
        if user.role.value == "admin":
            pass  # admins can access any session
        elif user.role.value in ("rop", "methodologist"):
            # ROP/methodologist can only view sessions from their team
            target_user = (await db.execute(
                select(User).where(User.id == session.user_id)
            )).scalar_one_or_none()
            if not target_user or target_user.team_id != user.team_id:
                raise HTTPException(status_code=403, detail="Not your team's session")
        else:
            raise HTTPException(status_code=403, detail="Not your session")
    if session.status != SessionStatus.completed:
        raise HTTPException(status_code=400, detail="Session must be completed to use Replay Mode")

    # ── 2. Load all messages ──
    msg_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.sequence_number)
    )
    all_messages = msg_result.scalars().all()

    # Find the target message
    target_msg = None
    target_index = -1
    for i, m in enumerate(all_messages):
        if m.id == message_id:
            target_msg = m
            target_index = i
            break

    if target_msg is None:
        raise HTTPException(status_code=404, detail="Message not found in this session")
    if target_msg.role != MessageRole.user:
        raise HTTPException(
            status_code=400,
            detail="Ideal response can only be generated for manager (user) messages",
        )

    # ── 3. Build context up to the target message ──
    # Get conversation history up to (but not including) the target message
    context_messages = all_messages[:target_index]
    # The client's last message before the manager's reply
    client_msg_before = None
    for m in reversed(context_messages):
        if m.role == MessageRole.assistant:
            client_msg_before = m
            break

    # Emotion state at this point in the conversation
    emotion_at_point = "cold"
    for m in reversed(context_messages):
        if m.emotion_state:
            emotion_at_point = m.emotion_state
            break

    # Build conversation lines for LLM context
    conversation_lines = []
    for i, m in enumerate(context_messages):
        role = "Менеджер" if m.role == MessageRole.user else "Клиент"
        emotion_tag = f" [{m.emotion_state}]" if m.emotion_state else ""
        conversation_lines.append(f"[{i}] {role}{emotion_tag}: {m.content}")

    # Limit context to last 40 messages to prevent token exhaustion
    if len(conversation_lines) > 40:
        conversation_lines = conversation_lines[-40:]
        conversation_lines.insert(0, "... (ранние реплики опущены) ...")
    conversation_text = "\n".join(conversation_lines) if conversation_lines else "(Начало разговора)"

    # ── 4. Extract scoring context ──
    scoring_details = session.scoring_details or {}
    score_ctx_parts = []

    # Stage progress at this point
    stage_data = scoring_details.get("_stage_progress", {})
    if stage_data:
        stages_completed = stage_data.get("stages_completed", [])
        stage_names = {
            1: "Приветствие", 2: "Контакт", 3: "Квалификация",
            4: "Презентация", 5: "Возражения", 6: "Встреча", 7: "Закрытие",
        }
        completed_names = [stage_names.get(s, str(s)) for s in stages_completed]
        score_ctx_parts.append(f"Пройденные этапы: {', '.join(completed_names) or 'нет'}.")

    # Layer explanations for weak areas
    layer_explanations = scoring_details.get("_layer_explanations", [])
    weak_layers = [le for le in layer_explanations if le.get("percentage", 100) < 60]
    if weak_layers:
        weak_lines = [f"  - {le.get('label', '?')}: {le.get('percentage', 0):.0f}% — {le.get('summary', '')}" for le in weak_layers[:4]]
        score_ctx_parts.append("Слабые области:\n" + "\n".join(weak_lines))

    # Skill radar
    skill_data = scoring_details.get("_skill_radar", {})
    if skill_data:
        weak_skills = {k: v for k, v in skill_data.items() if isinstance(v, (int, float)) and v < 60}
        if weak_skills:
            skill_lines = [f"  - {k}: {v:.0f}/100" for k, v in weak_skills.items()]
            score_ctx_parts.append("Навыки требующие улучшения:\n" + "\n".join(skill_lines))

    score_context = "\n".join(score_ctx_parts)

    # Trap context — check if any traps were active at this point
    trap_context = ""
    trap_handling_data = scoring_details.get("trap_handling", {})
    active_traps = trap_handling_data.get("traps", [])
    relevant_traps = []
    if active_traps and client_msg_before:
        for trap in active_traps:
            # Check if this trap was triggered around this message
            trap_msg_idx = trap.get("message_index")
            if trap_msg_idx is not None and abs(trap_msg_idx - target_index) <= 2:
                relevant_traps.append(trap)
        if relevant_traps:
            trap_lines = [
                f"  - {t.get('name', '?')} ({t.get('category', '?')}): статус={t.get('status', '?')}"
                for t in relevant_traps
            ]
            trap_context = "\nАктивные ловушки в этот момент:\n" + "\n".join(trap_lines)

    # ── 5. Build ideal-response prompt ──
    scenario_result = await db.execute(
        select(Scenario).where(Scenario.id == session.scenario_id)
    )
    scenario = scenario_result.scalar_one_or_none()

    ideal_prompt = (
        "Ты — эксперт-методолог по продажам банкротства физических лиц (127-ФЗ). "
        "Менеджер прошёл тренировку, и теперь анализирует свои ответы. "
        "Для указанной реплики менеджера нужно:\n"
        "1. Написать ИДЕАЛЬНЫЙ ответ — что менеджер ДОЛЖЕН БЫЛ сказать в этот момент.\n"
        "2. Объяснить ПОЧЕМУ этот ответ лучше — какие принципы продаж он применяет.\n"
        "3. Предсказать РЕАКЦИЮ клиента — как бы изменилось его эмоциональное состояние.\n"
        "4. Оценить ВЛИЯНИЕ на скоринг — какие слои улучшатся.\n\n"
        "Формат ответа (строго JSON):\n"
        "```json\n"
        "{\n"
        '  "ideal_text": "Идеальный ответ менеджера",\n'
        '  "explanation": "Почему этот ответ лучше (2-3 предложения)",\n'
        '  "emotion_prediction": "predicted_emotion_state",\n'
        '  "emotion_explanation": "Почему клиент перешёл бы в это состояние",\n'
        '  "layer_impact": {"L1": "+X", "L2": "+Y", "L3": "+Z"},\n'
        '  "score_delta_estimate": 5.0,\n'
        '  "trap_handling": [{"trap": "name", "original": "fell", "ideal": "dodged", "how": "explanation"}]\n'
        "}\n"
        "```\n\n"
        f"Сценарий: {scenario.title if scenario else '?'} (сложность {scenario.difficulty if scenario else '?'}/10)\n"
        f"Текущее эмоциональное состояние клиента: {emotion_at_point}\n"
        f"{score_context}\n"
        f"{trap_context}\n\n"
        f"=== РАЗГОВОР ДО ЭТОГО МОМЕНТА ===\n{conversation_text}\n\n"
        f"=== КЛИЕНТ СКАЗАЛ ===\n{client_msg_before.content if client_msg_before else '(начало разговора)'}\n\n"
        f"=== МЕНЕДЖЕР ОТВЕТИЛ (ОРИГИНАЛ) ===\n{target_msg.content}\n\n"
        "Сгенерируй идеальный ответ в формате JSON:"
    )

    # ── 6. Generate via LLM ──
    try:
        llm_result = await generate_response(
            system_prompt=ideal_prompt,
            messages=[{"role": "user", "content": "Сгенерируй идеальный ответ."}],
            emotion_state=emotion_at_point,
            user_id=f"replay:{user.id}",
            task_type="coach",
            prefer_provider="cloud",
        )
        raw_answer = llm_result.content
    except Exception as e:
        logger.error("Replay Mode LLM failed: %s", e)
        raise HTTPException(status_code=503, detail="AI temporarily unavailable")

    # ── 7. Parse JSON from LLM response ──
    import json as _json
    parsed: dict = {}
    try:
        # Extract JSON from markdown code block or raw JSON
        json_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw_answer, re.DOTALL)
        json_str = json_match.group(1).strip() if json_match else raw_answer.strip()
        parsed = _json.loads(json_str)
    except (_json.JSONDecodeError, AttributeError):
        # Fallback: treat entire response as explanation
        parsed = {
            "ideal_text": raw_answer[:500],
            "explanation": "LLM returned non-structured response.",
        }

    # ── 7b. Sanitize LLM output ──
    # Truncate fields to prevent oversized responses / prompt leakage
    _MAX_TEXT = 2000
    _MAX_EXPLANATION = 1000
    if "ideal_text" in parsed:
        parsed["ideal_text"] = str(parsed["ideal_text"])[:_MAX_TEXT]
    if "explanation" in parsed:
        parsed["explanation"] = str(parsed["explanation"])[:_MAX_EXPLANATION]
    if "emotion_explanation" in parsed:
        parsed["emotion_explanation"] = str(parsed["emotion_explanation"])[:_MAX_EXPLANATION]
    # Validate emotion prediction against known states
    _VALID_EMOTIONS = {
        "cold", "hostile", "hangup", "guarded", "testing", "curious",
        "callback", "considering", "negotiating", "deal",
        "skeptical", "warming", "open",
    }
    if parsed.get("emotion_prediction") and str(parsed["emotion_prediction"]) not in _VALID_EMOTIONS:
        parsed["emotion_prediction"] = None
    # Clamp score_delta_estimate to reasonable range
    if parsed.get("score_delta_estimate") is not None:
        try:
            delta_val = float(parsed["score_delta_estimate"])
            parsed["score_delta_estimate"] = max(-30, min(30, delta_val))
        except (TypeError, ValueError):
            parsed["score_delta_estimate"] = None
    # Sanitize layer_impact keys — only allow L1-L10
    if parsed.get("layer_impact") and isinstance(parsed["layer_impact"], dict):
        parsed["layer_impact"] = {
            k: str(v)[:10] for k, v in parsed["layer_impact"].items()
            if isinstance(k, str) and re.match(r"^L\d{1,2}$", k)
        }
    # Limit trap_handling entries
    if parsed.get("trap_handling") and isinstance(parsed["trap_handling"], list):
        parsed["trap_handling"] = [
            {
                "trap": str(t.get("trap", ""))[:100],
                "original": str(t.get("original", ""))[:20],
                "ideal": str(t.get("ideal", ""))[:20],
                "how": str(t.get("how", ""))[:200] if t.get("how") else None,
            }
            for t in parsed["trap_handling"][:5]
            if isinstance(t, dict)
        ]

    # ── 8. Compute score estimates ──
    original_total = float(session.score_total) if session.score_total else None
    score_delta = parsed.get("score_delta_estimate")
    ideal_estimate = None
    if original_total is not None and score_delta is not None:
        try:
            ideal_estimate = min(100, original_total + float(score_delta))
        except (TypeError, ValueError):
            pass

    # ── 9. Build response ──
    return IdealResponseResult(
        message_id=target_msg.id,
        message_index=target_index,
        original_text=target_msg.content,
        ideal_text=parsed.get("ideal_text", ""),
        explanation=parsed.get("explanation", ""),
        original_score_estimate=original_total,
        ideal_score_estimate=ideal_estimate,
        score_delta=float(score_delta) if score_delta else None,
        layer_impact=parsed.get("layer_impact"),
        original_emotion=emotion_at_point,
        ideal_emotion_prediction=parsed.get("emotion_prediction"),
        emotion_explanation=parsed.get("emotion_explanation"),
        trap_handling=parsed.get("trap_handling"),
    )
