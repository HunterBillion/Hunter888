import uuid
from datetime import datetime

from pydantic import BaseModel


class ScenarioResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    scenario_type: str
    difficulty: int
    estimated_duration_minutes: int
    character_name: str | None = None

    model_config = {"from_attributes": True}


class SessionStartRequest(BaseModel):
    scenario_id: uuid.UUID | None = None  # optional when using custom builder
    # Custom character builder params (all optional — used from Конструктор)
    custom_archetype: str | None = None       # e.g. "skeptic", "manipulator"
    custom_profession: str | None = None      # e.g. "budget", "entrepreneur"
    custom_lead_source: str | None = None     # e.g. "cold_base", "website_form"
    custom_difficulty: int | None = None       # 1-10
    # ── Constructor v2: new optional fields (DOC_02) ──
    # Step 3: Client context
    custom_family_preset: str | None = None       # "single", "married_kids" etc.
    custom_creditors_preset: str | None = None    # "1", "2_3", "4_5", "6_plus"
    custom_debt_stage: str | None = None          # "pre_court", "execution" etc.
    custom_debt_range: str | None = None          # "under_500k", "3m_10m" etc.
    # Step 4: Emotional preset
    custom_emotion_preset: str | None = None      # "neutral", "anxious", "angry" etc.
    # Step 6: Environment
    custom_bg_noise: str | None = None            # "none", "office", "street" etc.
    custom_time_of_day: str | None = None         # "morning", "afternoon" etc.
    custom_fatigue: str | None = None             # "fresh", "normal", "tired" etc.
    # Session mode — "chat" (default text) or "call" (phone-call voice mode).
    # Backend uses this to adapt LLM system prompt: call mode gets shorter,
    # more colloquial, interrupt-prone replies that feel like a real phone
    # conversation, not a drafted email.
    custom_session_mode: str | None = None        # "chat" | "call" | "center"
    # Tone / vibe (2026-04-21) — "harsh" | "neutral" | "lively" | "friendly"
    custom_tone: str | None = None
    # Custom character link
    custom_character_id: uuid.UUID | None = None  # link to saved CustomCharacter

    # ── 2026-04-23 Zone 1 — CRM-card → session linkage ──
    # When the user opens /clients/{id} and clicks «Написать»/«Позвонить»,
    # the frontend already sends real_client_id + source (e.g. "crm_chat",
    # "crm_voice"). Previously the schema dropped both fields silently,
    # so the WS handler never knew this was a real-client training and
    # always generated a random AI profile. Now we accept + persist them.
    real_client_id: uuid.UUID | None = None
    source: str | None = None

    # ── 2026-04-23 Zone 4 — retrain-flow via clone_from_session_id ──
    # When the user clicks «Повторить сценарий» on /results, the new
    # session is created by cloning all params of the previous one
    # (scenario_id, real_client_id, custom_character_id, custom_params,
    # session_mode). Frontend sends ONLY clone_from_session_id and the
    # backend does the copying — keeps the "retrain" contract in one place
    # and avoids the bug where frontend partially forgets parameters.
    clone_from_session_id: uuid.UUID | None = None

    # ── TZ-2 §6.2/6.3 canonical mode + runtime_type (Phase 4) ──
    # Frontend pages can now send these explicitly. When present, they
    # take precedence over the legacy ``custom_session_mode`` derivation;
    # missing values fall back to the Phase 0 derive_runtime_type rules
    # so older FE pages keep working unchanged.
    # Validation against MODES / RUNTIME_TYPES catalog happens in the
    # handler (via runtime_guard_engine when wired in Phase 3B); the
    # schema accepts free strings here so a typo gives a structured 400
    # GuardViolation instead of a generic 422 type error.
    mode: str | None = None
    runtime_type: str | None = None

    # TZ-2 §16.1 — strict schema. Unknown fields used to be silently
    # dropped, so any future canonical field (lead_client_id) added on
    # the frontend before the backend would vanish into the void with
    # no log. extra="forbid" surfaces the drift as a 422 immediately.
    model_config = {"extra": "forbid"}


class CustomCharacterCreate(BaseModel):
    name: str
    archetype: str
    profession: str
    lead_source: str
    difficulty: int = 5
    description: str | None = None
    # v2 fields
    family_preset: str | None = None
    creditors_preset: str | None = None
    debt_stage: str | None = None
    debt_range: str | None = None
    emotion_preset: str | None = None
    bg_noise: str | None = None
    time_of_day: str | None = None
    client_fatigue: str | None = None
    # 2026-04-21
    tone: str | None = None


class CustomCharacterUpdate(BaseModel):
    """Partial update — all fields optional."""
    name: str | None = None
    archetype: str | None = None
    profession: str | None = None
    lead_source: str | None = None
    difficulty: int | None = None
    description: str | None = None
    family_preset: str | None = None
    creditors_preset: str | None = None
    debt_stage: str | None = None
    debt_range: str | None = None
    emotion_preset: str | None = None
    bg_noise: str | None = None
    time_of_day: str | None = None
    client_fatigue: str | None = None
    tone: str | None = None


class CustomCharacterResponse(BaseModel):
    id: str
    name: str
    archetype: str
    profession: str
    lead_source: str
    difficulty: int
    description: str | None = None
    family_preset: str | None = None
    creditors_preset: str | None = None
    debt_stage: str | None = None
    debt_range: str | None = None
    emotion_preset: str | None = None
    bg_noise: str | None = None
    time_of_day: str | None = None
    client_fatigue: str | None = None
    tone: str | None = None
    play_count: int = 0
    best_score: int | None = None
    avg_score: int | None = None
    last_played_at: str | None = None
    created_at: str
    updated_at: str | None = None
    is_shared: bool = False
    share_code: str | None = None

    model_config = {"from_attributes": True}


class PreviewDossierRequest(BaseModel):
    archetype: str
    profession: str
    lead_source: str = "cold_base"
    family_preset: str | None = None
    creditors_preset: str | None = None
    debt_stage: str | None = None
    debt_range: str | None = None
    emotion_preset: str | None = None


class PreviewDossierResponse(BaseModel):
    dossier_text: str
    hints: list[str]
    generated_name: str
    generated_age: int
    generated_city: str


class SessionResponse(BaseModel):
    id: uuid.UUID
    scenario_id: uuid.UUID | None = None
    lead_client_id: uuid.UUID | None = None
    status: str
    # TZ-2 §6.2/6.3 canonical runtime fields. ORM already persists them
    # (training.py:159-160) but the schema dropped them, so the FE could
    # only read the legacy `custom_params.session_mode`. Surfacing them
    # here lets `training/[id]/call/page.tsx` fail-closed on a stale
    # legacy `session_mode` and trust the canonical `mode` instead.
    mode: str | None = None
    runtime_type: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    score_script_adherence: float | None = None
    score_objection_handling: float | None = None
    score_communication: float | None = None
    score_anti_patterns: float | None = None
    score_result: float | None = None
    score_total: float | None = None
    # FIND-007 fix: Wave 5 layered scoring (L6-L10). Backend computes these
    # into ORM columns; Pydantic used to drop them by silent validation.
    score_chain_traversal: float | None = None
    score_trap_handling: float | None = None
    score_human_factor: float | None = None
    score_narrative: float | None = None
    score_legal: float | None = None
    scoring_details: dict | None = None
    emotion_timeline: list | None = None
    feedback_text: str | None = None
    client_story_id: uuid.UUID | None = None
    call_number_in_story: int | None = None
    custom_params: dict | None = None
    # 2026-04-23 Sprint 4 — expose linkage fields so /results can route the
    # «Повторить сценарий» button into the correct pit-stop (CRM card vs
    # SavedTab vs direct clone). Already persisted on TrainingSession; used
    # to be silently dropped by Pydantic.
    real_client_id: uuid.UUID | None = None
    custom_character_id: uuid.UUID | None = None
    source_session_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    emotion_state: str | None = None
    sequence_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TrapResultItem(BaseModel):
    """Trap result formatted for frontend TrapResults component."""
    name: str
    caught: bool
    bonus: int | None = None
    penalty: int | None = None
    status: str | None = None  # fell | dodged | partial
    client_phrase: str | None = None
    correct_example: str | None = None
    explanation: str | None = None
    law_reference: str | None = None
    correct_keywords: list[str] | None = None
    wrong_keywords: list[str] | None = None
    category: str | None = None


class SoftSkillsResult(BaseModel):
    """Soft skills formatted for frontend SoftSkillsCard component."""
    avg_response_time_sec: float = 0.0
    talk_listen_ratio: float = 0.5
    name_usage_count: int = 0
    interruptions: int = 0
    avg_message_length: float = 0.0


class StoryCallSummary(BaseModel):
    session_id: uuid.UUID
    call_number: int
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    score_total: float | None = None
    score_human_factor: float | None = None
    score_narrative: float | None = None
    score_legal: float | None = None


class StorySummaryResponse(BaseModel):
    id: uuid.UUID
    story_name: str
    total_calls_planned: int
    current_call_number: int
    is_completed: bool
    game_status: str
    tension: float
    tension_curve: list[float] = []
    pacing: str | None = None
    next_twist: str | None = None
    active_factors: list[dict] = []
    between_call_events: list[dict] = []
    consequences: list[dict] = []
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    completed_calls: int = 0
    avg_score: float | None = None
    best_score: float | None = None
    latest_session_id: uuid.UUID | None = None


class HistoryEntryResponse(BaseModel):
    kind: str
    sort_at: datetime
    latest_session: SessionResponse
    story: StorySummaryResponse | None = None
    sessions: list[StoryCallSummary] = []
    calls_completed: int = 1
    avg_score: float | None = None
    best_score: float | None = None


class WeakLegalCategory(BaseModel):
    """Weak legal area detected from L10 scoring — links to Knowledge Quiz."""
    category: str
    display_name: str
    accuracy_pct: int
    article_refs: list[str] = []


class PromiseFulfillment(BaseModel):
    """Promise tracking from Game CRM multi-call stories."""
    text: str
    call_number: int
    fulfilled: bool
    impact: str  # "bonus" | "penalty" | "neutral"


class SessionResultResponse(BaseModel):
    session: SessionResponse
    messages: list[MessageResponse]
    score_breakdown: dict | None = None
    trap_results: list[TrapResultItem] | None = None
    soft_skills: SoftSkillsResult | None = None
    client_card: dict | None = None
    story: StorySummaryResponse | None = None
    story_calls: list[StoryCallSummary] = []
    weak_legal_categories: list[WeakLegalCategory] | None = None
    promise_fulfillment: list[PromiseFulfillment] | None = None
    # FIND-006 fix: XP + level-up rewards. WS /ws/training emits these at
    # session.end; HTTP GET /sessions/{id} used to drop them because they
    # weren't declared here — frontend silently missed XP animations.
    xp_breakdown: dict | None = None
    level_up: bool | None = None
    new_level: int | None = None
    new_level_name: str | None = None


# ── Wave 5: Replay Mode ──────────────────────────────────────────────────────


class IdealResponseResult(BaseModel):
    """Result of generating an ideal response for a specific message in a session."""
    message_id: uuid.UUID
    message_index: int
    original_text: str
    ideal_text: str
    explanation: str
    # Scoring comparison
    original_score_estimate: float | None = None
    ideal_score_estimate: float | None = None
    score_delta: float | None = None
    # Per-layer impact (key layers only)
    layer_impact: dict | None = None  # e.g. {"L2": "+3.5", "L3": "+1.2", "L8": "+2.0"}
    # Emotion prediction
    original_emotion: str | None = None
    ideal_emotion_prediction: str | None = None
    emotion_explanation: str | None = None
    # Trap handling
    trap_handling: list[dict] | None = None  # [{"trap": "...", "original": "fell", "ideal": "dodged"}]
