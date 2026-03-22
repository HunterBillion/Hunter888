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


class SessionResponse(BaseModel):
    id: uuid.UUID
    scenario_id: uuid.UUID | None = None
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    score_script_adherence: float | None = None
    score_objection_handling: float | None = None
    score_communication: float | None = None
    score_anti_patterns: float | None = None
    score_result: float | None = None
    score_total: float | None = None
    scoring_details: dict | None = None
    emotion_timeline: list | None = None
    feedback_text: str | None = None
    client_story_id: uuid.UUID | None = None
    call_number_in_story: int | None = None
    custom_params: dict | None = None

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


class SessionResultResponse(BaseModel):
    session: SessionResponse
    messages: list[MessageResponse]
    score_breakdown: dict | None = None
    trap_results: list[TrapResultItem] | None = None
    soft_skills: SoftSkillsResult | None = None
    client_card: dict | None = None
    story: StorySummaryResponse | None = None
    story_calls: list[StoryCallSummary] = []
