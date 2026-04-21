"""
ТЗ-02/03: API routes для эмоций, ловушек и цепочек возражений.

Эндпоинты:
  GET  /api/emotion/{session_id}           — текущее состояние эмоций
  POST /api/emotion/{session_id}/trigger   — обработать триггер
  POST /api/emotion/{session_id}/init      — инициализировать сессию эмоций
  GET  /api/emotion/{session_id}/prompt    — данные для system prompt

  GET  /api/traps                          — список ловушек (фильтры)
  POST /api/traps/evaluate                 — оценить ответ на ловушку
  GET  /api/traps/session/{session_id}     — статистика ловушек за сессию
  POST /api/traps/select                   — выбрать ловушку для хода

  GET  /api/chains                         — список цепочек (фильтры)
  POST /api/chains/start                   — начать цепочку
  POST /api/chains/respond                 — обработать ответ на шаг цепочки
  GET  /api/chains/session/{session_id}    — состояние цепочки сессии

  POST /api/cascades/start                 — начать каскад
  POST /api/cascades/outcome               — обработать исход каскада
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core import errors as err
from app.core.deps import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["emotion", "traps", "chains"])


# ════════════════════════════════════════════════════════════════════
#  Pydantic Schemas
# ════════════════════════════════════════════════════════════════════

# ── Emotion ──

class EmotionInitRequest(BaseModel):
    archetype_code: str
    initial_state: str = "cold"
    difficulty_modifier: int = 0


class EmotionTriggerRequest(BaseModel):
    trigger_code: str
    archetype_override: str | None = None


class EmotionStateResponse(BaseModel):
    session_id: str
    current_state: str
    display_state: str
    energy: float
    energy_smoothed: float
    mood_zone: str
    turn_number: int
    fake_active: bool
    recent_transitions: list[dict] = []


class EmotionTriggerResponse(BaseModel):
    previous_state: str
    new_state: str
    display_state: str
    trigger_code: str
    energy_delta: float
    energy_after: float
    energy_smoothed: float
    mood_zone: str
    is_fake: bool
    fake_revealed: bool
    counter_triggered: list[str] = []
    state_changed: bool


class EmotionPromptResponse(BaseModel):
    state: str
    display_state: str
    energy: float
    mood: str
    fake_active: bool
    turn: int
    recent: list[dict] = []


# ── Traps ──

class TrapEvaluateRequest(BaseModel):
    session_id: str
    trap_code: str
    manager_message: str


class TrapEvaluateResponse(BaseModel):
    trap_code: str
    outcome: str
    detection_method: str
    confidence: float
    score_delta: int
    reason: str = ""
    emotion_trigger: str = ""
    cascade_next: str | None = None


class TrapSelectRequest(BaseModel):
    session_id: str
    archetype_code: str
    emotion_state: str
    profession_code: str = ""
    effective_difficulty: int = 5
    trap_probability: float = 0.15


class TrapSelectResponse(BaseModel):
    trap_code: str | None = None
    trap_name: str | None = None
    client_phrase: str | None = None
    difficulty: int | None = None
    category: str | None = None
    has_trap: bool = False


class TrapSessionStatsResponse(BaseModel):
    session_id: str
    trap_count: int
    fell_count: int
    dodged_count: int
    total_penalty: int
    total_bonus: int
    encountered_traps: list[str] = []
    fell_traps: list[str] = []
    dodged_traps: list[str] = []


class TrapListItem(BaseModel):
    code: str
    name: str
    category: str
    difficulty: int
    client_phrase: str


# ── Chains ──

class ChainStartRequest(BaseModel):
    session_id: str
    chain_code: str


class ChainRespondRequest(BaseModel):
    session_id: str
    chain_code: str
    response_quality: str   # good | bad | skip
    trap_outcome: str | None = None


class ChainStepResponse(BaseModel):
    chain_code: str
    step_order: int
    client_text: str
    category: str
    has_trap: bool
    trap_code: str | None = None
    outcome: str = ""
    next_step: int | None = None
    exit_code: str | None = None
    chain_completed: bool = False
    chain_result: str = ""


class ChainSessionResponse(BaseModel):
    session_id: str
    active_chain_code: str | None = None
    current_step: int
    chain_completed: bool
    chain_result: str
    chains_completed: list[str] = []
    total_chains: int
    good_responses: int
    bad_responses: int


class ChainListItem(BaseModel):
    code: str
    name: str
    difficulty: int
    archetype_codes: list[str] = []


# ── Cascades ──

class CascadeStartRequest(BaseModel):
    session_id: str
    cascade_code: str


class CascadeOutcomeRequest(BaseModel):
    session_id: str
    cascade_code: str
    trap_outcome: str  # fell | dodged | partial


class CascadeOutcomeResponse(BaseModel):
    completed: bool
    next_trap_code: str | None = None
    emotion_trigger: str = ""
    penalty_multiplier: float = 1.0


# ════════════════════════════════════════════════════════════════════
#  Dependency wiring — адаптеры к функциональным сервисам
# ════════════════════════════════════════════════════════════════════

import uuid as _uuid
from dataclasses import dataclass, field as dc_field
from app.services.emotion import (
    init_emotion_v3,
    get_emotion,
    get_emotion_timeline,
    transition_emotion_v3,
    cleanup_emotion,
    get_fake_prompt,
    ARCHETYPE_CONFIGS,
    _get_mood_buffer,
    _get_memory,
    _get_fake,
)
from app.services.trap_detector import (
    detect_traps as _detect_traps,
    get_session_trap_state,
    TrapResult,
    TrapSessionState,
)
from app.services.objection_chain import (
    init_chain as _init_chain,
    advance_chain as _advance_chain,
    get_chain_state as _get_chain_state,
)
from app.models.character import EmotionState, LEGACY_MAP


# --- Emotion Engine Adapter ---

@dataclass
class _EmotionState:
    current_state: str = "cold"
    energy: float = 0.0
    energy_smoothed: float = 0.0
    mood_zone: str = "neutral"
    turn_number: int = 0
    fake_active: bool = False
    fake_display_state: str | None = None
    threshold_positive: float = 5.0
    threshold_negative: float = -5.0
    recent_transitions: list = dc_field(default_factory=list)


@dataclass
class _TriggerResult:
    previous_state: str = "cold"
    new_state: str = "cold"
    display_state: str = "cold"
    trigger_code: str = ""
    energy_delta: float = 0.0
    energy_after: float = 0.0
    energy_smoothed: float = 0.0
    mood_zone: str = "neutral"
    is_fake: bool = False
    fake_revealed: bool = False
    counter_triggered: list = dc_field(default_factory=list)
    state_changed: bool = False


class _EmotionEngineAdapter:
    """Адаптер: оборачивает функциональный API emotion.py в ООП-интерфейс для роутов."""

    async def init_session(
        self, session_id: str, archetype_code: str,
        initial_state: str = "cold", difficulty_modifier: int = 0,
    ) -> _EmotionState:
        sid = _uuid.UUID(session_id)
        state_name = await init_emotion_v3(sid, archetype_code)
        buffer = await _get_mood_buffer(sid)
        config = ARCHETYPE_CONFIGS.get(archetype_code, ARCHETYPE_CONFIGS["skeptic"])
        return _EmotionState(
            current_state=state_name,
            energy=buffer.current_energy,
            energy_smoothed=buffer.energy_smoothed,
            threshold_positive=config.threshold_positive,
            threshold_negative=config.threshold_negative,
        )

    async def get_state(self, session_id: str) -> _EmotionState | None:
        sid = _uuid.UUID(session_id)
        state_name = await get_emotion(sid)
        if not state_name:
            return None
        buffer = await _get_mood_buffer(sid)
        fake = await _get_fake(sid)
        memory = await _get_memory(sid)
        timeline = await get_emotion_timeline(sid)
        mood = (
            "positive" if buffer.energy_smoothed >= buffer.threshold_positive
            else "negative" if buffer.energy_smoothed <= buffer.threshold_negative
            else "neutral"
        )
        return _EmotionState(
            current_state=state_name,
            energy=buffer.current_energy,
            energy_smoothed=buffer.energy_smoothed,
            mood_zone=mood,
            turn_number=len(timeline),
            fake_active=fake is not None and not fake.revealed,
            fake_display_state=fake.display_state if fake and not fake.revealed else None,
            threshold_positive=buffer.threshold_positive,
            threshold_negative=buffer.threshold_negative,
            recent_transitions=timeline[-5:] if timeline else [],
        )

    async def process_trigger(
        self, session_id: str, trigger_code: str,
        archetype_override: str | None = None,
    ) -> _TriggerResult:
        sid = _uuid.UUID(session_id)
        state_before = await get_emotion(sid) or "cold"
        buffer_before = await _get_mood_buffer(sid)
        energy_before = buffer_before.current_energy

        archetype = archetype_override or "skeptic"
        new_state, meta = await transition_emotion_v3(
            sid, archetype, [trigger_code],
        )

        buffer_after = await _get_mood_buffer(sid)
        fake = await _get_fake(sid)
        mood = (
            "positive" if buffer_after.energy_smoothed >= buffer_after.threshold_positive
            else "negative" if buffer_after.energy_smoothed <= buffer_after.threshold_negative
            else "neutral"
        )
        display = fake.display_state if fake and not fake.revealed else new_state
        return _TriggerResult(
            previous_state=state_before,
            new_state=new_state,
            display_state=LEGACY_MAP.get(EmotionState(display), display) if display else new_state,
            trigger_code=trigger_code,
            energy_delta=meta.get("energy_delta", 0),
            energy_after=meta.get("energy_after", buffer_after.current_energy),
            energy_smoothed=meta.get("energy_smoothed", buffer_after.energy_smoothed),
            mood_zone=mood,
            is_fake=meta.get("is_fake", False),
            fake_revealed=False,
            state_changed=state_before != new_state,
        )

    async def get_prompt_context(self, session_id: str) -> dict:
        sid = _uuid.UUID(session_id)
        state = await get_emotion(sid) or "cold"
        buffer = await _get_mood_buffer(sid)
        fake = await _get_fake(sid)
        timeline = await get_emotion_timeline(sid)
        mood = (
            "positive" if buffer.energy_smoothed >= buffer.threshold_positive
            else "negative" if buffer.energy_smoothed <= buffer.threshold_negative
            else "neutral"
        )
        display = fake.display_state if fake and not fake.revealed else state
        return {
            "state": state,
            "display_state": LEGACY_MAP.get(EmotionState(display), display) if display else state,
            "energy": buffer.current_energy,
            "mood": mood,
            "fake_active": fake is not None and not fake.revealed,
            "turn": len(timeline),
            "recent": timeline[-5:] if timeline else [],
        }


# --- Trap / Chain Data Adapters ---

@dataclass
class _TrapData:
    code: str
    name: str
    category: str
    difficulty: int
    client_phrase: str
    archetype_codes: list = dc_field(default_factory=list)
    keywords: list = dc_field(default_factory=list)
    regex_patterns: list = dc_field(default_factory=list)
    penalty: int = 0
    bonus: int = 0


# In-memory cache loaded from seed_traps at import time
_TRAP_CACHE: dict[str, _TrapData] = {}
_CHAIN_CACHE: dict[str, dict] = {}
_CASCADE_CACHE: dict[str, dict] = {}
_CACHE_LOADED = False


async def _ensure_cache():
    """Лениво загружает trap/chain/cascade данные из seed-скриптов в память."""
    global _CACHE_LOADED
    if _CACHE_LOADED:
        return
    try:
        from scripts.seed_traps import TRAP_DEFINITIONS, OBJECTION_CHAINS, CASCADE_DEFINITIONS
        for t in TRAP_DEFINITIONS:
            _TRAP_CACHE[t["code"]] = _TrapData(
                code=t["code"], name=t["name"], category=t["category"],
                difficulty=t["difficulty"], client_phrase=t["client_phrase"],
                archetype_codes=t.get("archetype_codes", []),
                keywords=t.get("keywords", []),
                regex_patterns=t.get("regex_patterns", []),
                penalty=t.get("penalty", 0), bonus=t.get("bonus", 0),
            )
        for c in OBJECTION_CHAINS:
            _CHAIN_CACHE[c["code"]] = c
        if CASCADE_DEFINITIONS:
            for cs in CASCADE_DEFINITIONS:
                _CASCADE_CACHE[cs["code"]] = cs
    except ImportError:
        logger.warning("seed_traps not available — trap cache empty")
    _CACHE_LOADED = True


# --- DI Provider Functions ---

async def get_emotion_engine() -> _EmotionEngineAdapter:
    return _EmotionEngineAdapter()


async def get_trap_detector():
    """Возвращает модуль trap_detector (функциональный API используется напрямую в эндпоинтах)."""
    return None  # эндпоинты переписаны ниже для прямого вызова


async def get_chain_service():
    """Возвращает None — chain-эндпоинты используют функциональный API напрямую."""
    return None


async def get_trap_data_by_code(trap_code: str) -> _TrapData | None:
    await _ensure_cache()
    return _TRAP_CACHE.get(trap_code)


async def get_all_trap_data() -> list[_TrapData]:
    await _ensure_cache()
    return list(_TRAP_CACHE.values())


async def get_chain_data_by_code(chain_code: str) -> dict | None:
    await _ensure_cache()
    return _CHAIN_CACHE.get(chain_code)


async def get_cascade_data_by_code(cascade_code: str) -> dict | None:
    await _ensure_cache()
    return _CASCADE_CACHE.get(cascade_code)


# ════════════════════════════════════════════════════════════════════
#  EMOTION ENDPOINTS
# ════════════════════════════════════════════════════════════════════

@router.post(
    "/emotion/{session_id}/init",
    response_model=EmotionStateResponse,
    summary="Инициализировать эмоциональное состояние сессии",
)
@limiter.limit("15/minute")
async def emotion_init(request: Request, session_id: str, body: EmotionInitRequest, user: User = Depends(get_current_user)):
    engine = await get_emotion_engine()
    state = await engine.init_session(
        session_id=session_id,
        archetype_code=body.archetype_code,
        initial_state=body.initial_state,
        difficulty_modifier=body.difficulty_modifier,
    )
    display = state.fake_display_state if state.fake_active else state.current_state
    mood = (
        "positive" if state.energy_smoothed >= state.threshold_positive
        else "negative" if state.energy_smoothed <= state.threshold_negative
        else "neutral"
    )
    return EmotionStateResponse(
        session_id=session_id,
        current_state=state.current_state,
        display_state=display,
        energy=state.energy,
        energy_smoothed=state.energy_smoothed,
        mood_zone=mood,
        turn_number=state.turn_number,
        fake_active=state.fake_active,
        recent_transitions=state.recent_transitions,
    )


@router.get(
    "/emotion/{session_id}",
    response_model=EmotionStateResponse,
    summary="Получить текущее состояние эмоций",
)
async def emotion_get(session_id: str, user: User = Depends(get_current_user)):
    engine = await get_emotion_engine()
    state = await engine.get_state(session_id)
    if state is None:
        raise HTTPException(404, detail=err.EMOTION_STATE_NOT_FOUND)

    display = state.fake_display_state if state.fake_active else state.current_state
    mood = (
        "positive" if state.energy_smoothed >= state.threshold_positive
        else "negative" if state.energy_smoothed <= state.threshold_negative
        else "neutral"
    )
    return EmotionStateResponse(
        session_id=session_id,
        current_state=state.current_state,
        display_state=display,
        energy=state.energy,
        energy_smoothed=state.energy_smoothed,
        mood_zone=mood,
        turn_number=state.turn_number,
        fake_active=state.fake_active,
        recent_transitions=state.recent_transitions,
    )


@router.post(
    "/emotion/{session_id}/trigger",
    response_model=EmotionTriggerResponse,
    summary="Обработать триггер перехода",
)
@limiter.limit("15/minute")
async def emotion_trigger(request: Request, session_id: str, body: EmotionTriggerRequest, user: User = Depends(get_current_user)):
    engine = await get_emotion_engine()
    result = await engine.process_trigger(
        session_id=session_id,
        trigger_code=body.trigger_code,
        archetype_override=body.archetype_override,
    )
    return EmotionTriggerResponse(
        previous_state=result.previous_state,
        new_state=result.new_state,
        display_state=result.display_state,
        trigger_code=result.trigger_code,
        energy_delta=result.energy_delta,
        energy_after=result.energy_after,
        energy_smoothed=result.energy_smoothed,
        mood_zone=result.mood_zone,
        is_fake=result.is_fake,
        fake_revealed=result.fake_revealed,
        counter_triggered=result.counter_triggered,
        state_changed=result.state_changed,
    )


@router.get(
    "/emotion/{session_id}/prompt",
    response_model=EmotionPromptResponse,
    summary="Данные для инъекции в system prompt",
)
async def emotion_prompt(session_id: str, user: User = Depends(get_current_user)):
    engine = await get_emotion_engine()
    ctx = await engine.get_prompt_context(session_id)
    return EmotionPromptResponse(**ctx)


# ════════════════════════════════════════════════════════════════════
#  TRAP ENDPOINTS
# ════════════════════════════════════════════════════════════════════

@router.get(
    "/traps",
    response_model=list[TrapListItem],
    summary="Список ловушек с фильтрами",
)
async def traps_list(
    category: str | None = Query(None),
    max_difficulty: int = Query(10, ge=1, le=10),
    archetype: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    all_traps = await get_all_trap_data()

    filtered = all_traps
    if category:
        filtered = [t for t in filtered if t.category == category]
    if archetype:
        filtered = [t for t in filtered if archetype in t.archetype_codes]
    filtered = [t for t in filtered if t.difficulty <= max_difficulty]

    page = filtered[offset:offset + limit]
    return [
        TrapListItem(
            code=t.code, name=t.name, category=t.category,
            difficulty=t.difficulty, client_phrase=t.client_phrase,
        )
        for t in page
    ]


@router.post(
    "/traps/evaluate",
    response_model=TrapEvaluateResponse,
    summary="Оценить ответ менеджера на ловушку",
)
@limiter.limit("15/minute")
async def traps_evaluate(request: Request, body: TrapEvaluateRequest, user: User = Depends(get_current_user)):
    from app.services.trap_detector import analyze_response as _analyze_response

    trap_data = await get_trap_data_by_code(body.trap_code)
    if trap_data is None:
        raise HTTPException(404, detail=f"Trap {body.trap_code} not found")

    trap_dict = {
        "code": trap_data.code,
        "name": trap_data.name,
        "category": trap_data.category,
        "difficulty": trap_data.difficulty,
        "client_phrase": trap_data.client_phrase,
        "keywords": trap_data.keywords,
        "regex_patterns": trap_data.regex_patterns,
        "penalty": trap_data.penalty,
        "bonus": trap_data.bonus,
    }
    result = await _analyze_response(
        session_id=_uuid.UUID(body.session_id),
        trap=trap_dict,
        manager_message=body.manager_message,
    )
    return TrapEvaluateResponse(
        trap_code=result.trap_code,
        outcome=result.outcome,
        detection_method=result.detection_method,
        confidence=result.confidence,
        score_delta=result.score_delta,
        reason=result.reason,
        emotion_trigger=result.emotion_trigger,
        cascade_next=getattr(result, "cascade_next", None),
    )


@router.post(
    "/traps/select",
    response_model=TrapSelectResponse,
    summary="Выбрать ловушку для текущего хода",
)
@limiter.limit("15/minute")
async def traps_select(request: Request, body: TrapSelectRequest, user: User = Depends(get_current_user)):
    """Выбирает ловушку по фильтрам: архетип, эмоция, сложность, вероятность."""
    import random

    all_traps = await get_all_trap_data()

    # Фильтрация по архетипу и сложности
    candidates = [
        t for t in all_traps
        if t.difficulty <= body.effective_difficulty
        and (not t.archetype_codes or body.archetype_code in t.archetype_codes)
    ]

    if not candidates or random.random() > body.trap_probability:
        return TrapSelectResponse(has_trap=False)

    trap = random.choice(candidates)
    return TrapSelectResponse(
        trap_code=trap.code,
        trap_name=trap.name,
        client_phrase=trap.client_phrase,
        difficulty=trap.difficulty,
        category=trap.category,
        has_trap=True,
    )


@router.get(
    "/traps/session/{session_id}",
    response_model=TrapSessionStatsResponse,
    summary="Статистика ловушек за сессию",
)
async def traps_session_stats(session_id: str, user: User = Depends(get_current_user)):
    stats = await get_session_trap_state(_uuid.UUID(session_id))
    return TrapSessionStatsResponse(
        session_id=session_id,
        trap_count=stats.trap_count,
        fell_count=len(stats.fell_traps),
        dodged_count=len(stats.dodged_traps),
        total_penalty=stats.total_penalty,
        total_bonus=stats.total_bonus,
        encountered_traps=stats.encountered_traps,
        fell_traps=stats.fell_traps,
        dodged_traps=stats.dodged_traps,
    )


# ════════════════════════════════════════════════════════════════════
#  CHAIN ENDPOINTS
# ════════════════════════════════════════════════════════════════════

@router.get(
    "/chains",
    response_model=list[ChainListItem],
    summary="Список цепочек возражений",
)
async def chains_list(
    archetype: str | None = Query(None),
    max_difficulty: int = Query(10, ge=1, le=10),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(get_current_user),
):
    await _ensure_cache()
    items = []
    for code, chain in _CHAIN_CACHE.items():
        diff = chain.get("difficulty", 5)
        if diff > max_difficulty:
            continue
        arch_codes = chain.get("archetype_codes", [])
        if archetype and archetype not in arch_codes:
            continue
        items.append(ChainListItem(
            code=code,
            name=chain.get("name", code),
            difficulty=diff,
            archetype_codes=arch_codes,
        ))
        if len(items) >= limit:
            break
    return items


@router.post(
    "/chains/start",
    response_model=ChainStepResponse,
    summary="Начать цепочку возражений",
)
@limiter.limit("10/minute")
async def chains_start(request: Request, body: ChainStartRequest, user: User = Depends(get_current_user)):
    chain = await get_chain_data_by_code(body.chain_code)
    if chain is None:
        raise HTTPException(404, detail=f"Chain {body.chain_code} not found")

    sid = _uuid.UUID(body.session_id)
    steps = chain.get("steps", [])
    await _init_chain(sid, steps)
    first_step = steps[0] if steps else {}
    return ChainStepResponse(
        chain_code=body.chain_code,
        step_order=0,
        client_text=first_step.get("client_text", ""),
        category=first_step.get("category", ""),
        has_trap=first_step.get("has_trap", False),
        trap_code=first_step.get("trap_code"),
    )


@router.post(
    "/chains/respond",
    response_model=ChainStepResponse,
    summary="Обработать ответ менеджера на шаг цепочки",
)
@limiter.limit("15/minute")
async def chains_respond(request: Request, body: ChainRespondRequest, user: User = Depends(get_current_user)):
    chain = await get_chain_data_by_code(body.chain_code)
    if chain is None:
        raise HTTPException(404, detail=f"Chain {body.chain_code} not found")

    sid = _uuid.UUID(body.session_id)
    result = await _advance_chain(sid, body.response_quality)
    state = await _get_chain_state(sid) or {}

    current_step_idx = state.get("current_step", 0)
    steps = chain.get("steps", [])
    step = steps[current_step_idx] if current_step_idx < len(steps) else {}
    completed = state.get("chain_completed", False)

    return ChainStepResponse(
        chain_code=body.chain_code,
        step_order=current_step_idx,
        client_text=step.get("client_text", result) if not completed else "",
        category=step.get("category", ""),
        has_trap=step.get("has_trap", False),
        trap_code=step.get("trap_code"),
        outcome=body.response_quality,
        next_step=current_step_idx + 1 if not completed else None,
        chain_completed=completed,
        chain_result=state.get("chain_result", ""),
    )


@router.get(
    "/chains/session/{session_id}",
    response_model=ChainSessionResponse,
    summary="Состояние цепочки за сессию",
)
async def chains_session(session_id: str, user: User = Depends(get_current_user)):
    sid = _uuid.UUID(session_id)
    state = await _get_chain_state(sid) or {}
    return ChainSessionResponse(
        session_id=session_id,
        active_chain_code=state.get("active_chain_code"),
        current_step=state.get("current_step", 0),
        chain_completed=state.get("chain_completed", False),
        chain_result=state.get("chain_result", ""),
        chains_completed=state.get("chains_completed", []),
        total_chains=state.get("total_chains", 0),
        good_responses=state.get("good_responses", 0),
        bad_responses=state.get("bad_responses", 0),
    )


# ════════════════════════════════════════════════════════════════════
#  CASCADE ENDPOINTS
# ════════════════════════════════════════════════════════════════════

@router.post(
    "/cascades/start",
    summary="Начать каскадную цепочку",
)
@limiter.limit("10/minute")
async def cascades_start(request: Request, body: CascadeStartRequest, user: User = Depends(get_current_user)):
    cascade = await get_cascade_data_by_code(body.cascade_code)
    if cascade is None:
        raise HTTPException(404, detail=f"Cascade {body.cascade_code} not found")

    levels = cascade.get("levels", [])
    first_trap_code = levels[0].get("trap_code") if levels else None
    return {"cascade_code": body.cascade_code, "first_trap_code": first_trap_code}


@router.post(
    "/cascades/outcome",
    response_model=CascadeOutcomeResponse,
    summary="Обработать исход ловушки каскада",
)
@limiter.limit("15/minute")
async def cascades_outcome(request: Request, body: CascadeOutcomeRequest, user: User = Depends(get_current_user)):
    cascade = await get_cascade_data_by_code(body.cascade_code)
    if cascade is None:
        raise HTTPException(404, detail=f"Cascade {body.cascade_code} not found")

    levels = cascade.get("levels", [])
    # Простая логика: если fell — следующий уровень, если dodged — каскад завершён
    if body.trap_outcome == "dodged":
        return CascadeOutcomeResponse(completed=True)

    # fell/partial — ищем следующий уровень
    next_trap = None
    for i, level in enumerate(levels):
        if level.get("trap_code") and i > 0:
            next_trap = level["trap_code"]
            break

    return CascadeOutcomeResponse(
        completed=next_trap is None,
        next_trap_code=next_trap,
        emotion_trigger=cascade.get("emotion_trigger_on_fail", ""),
        penalty_multiplier=cascade.get("penalty_multiplier", 1.0),
    )
