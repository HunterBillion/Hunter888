import enum
import json
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base


class NormalizedJSONB(TypeDecorator):
    """JSONB bind: coerce accidental str 'null' / JSON text to dict|list|None for asyncpg."""

    impl = JSONB
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            s = value.strip()
            if not s or s.lower() == "null":
                return None
            try:
                return json.loads(s)
            except (json.JSONDecodeError, TypeError):
                return None
        return value


class SessionStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"
    error = "error"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=False, index=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus), default=SessionStatus.active
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    # 5-layer scoring (from TZ section 7.6)
    score_script_adherence: Mapped[float | None] = mapped_column(Float)
    score_objection_handling: Mapped[float | None] = mapped_column(Float)
    score_communication: Mapped[float | None] = mapped_column(Float)
    score_anti_patterns: Mapped[float | None] = mapped_column(Float)
    score_result: Mapped[float | None] = mapped_column(Float)
    score_total: Mapped[float | None] = mapped_column(Float)

    scoring_details: Mapped[dict | None] = mapped_column(NormalizedJSONB)
    emotion_timeline: Mapped[dict | None] = mapped_column(NormalizedJSONB)
    checkpoints_reached: Mapped[dict | None] = mapped_column(NormalizedJSONB)
    feedback_text: Mapped[str | None] = mapped_column(Text)

    # v5 scoring: Layer 8 — Human Factor Handling (up to 15 pts)
    score_human_factor: Mapped[float | None] = mapped_column(Float)
    # v5 scoring: Layer 9 — Narrative Progression (up to 10 pts, post-session)
    score_narrative: Mapped[float | None] = mapped_column(Float)
    # v5 scoring: Layer 10 — Legal Accuracy (±5 modifier, post-session)
    score_legal: Mapped[float | None] = mapped_column(Float)

    # Link to multi-call story (nullable for single-call sessions)
    client_story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_stories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    call_number_in_story: Mapped[int | None] = mapped_column(Integer)

    # Custom character builder params (from Конструктор)
    custom_params: Mapped[dict | None] = mapped_column(NormalizedJSONB)

    # Phase 2: Link to real CRM client (for "потренируйся на клиенте X")
    real_client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("real_clients.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_session_seq", "session_id", "sequence_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    audio_duration_ms: Mapped[int | None] = mapped_column(Integer)
    stt_confidence: Mapped[float | None] = mapped_column(Float)
    emotion_state: Mapped[str | None] = mapped_column(String(50))
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    llm_model: Mapped[str | None] = mapped_column(String(100))
    llm_latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssignedTraining(Base):
    __tablename__ = "assigned_trainings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True
    )
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# v5 Models — Multi-call sessions, call records, session reports
# ---------------------------------------------------------------------------

class MultiCallSessionStatus(str, enum.Enum):
    """Status for a multi-call story session grouping."""
    planning = "planning"          # Story being set up
    in_progress = "in_progress"    # Active story, calls ongoing
    between_calls = "between_calls" # Between calls, CRM events active
    completed = "completed"        # All calls done, report generated
    abandoned = "abandoned"        # User left mid-story


class CallRecord(Base):
    """Per-call metadata within a multi-call story.

    Links a TrainingSession to its parent ClientStory and tracks
    call-specific context: pre-call brief, between-call events,
    emotion trajectory, and call outcome.
    """
    __tablename__ = "call_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    call_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pre-call brief shown to manager
    pre_call_brief: Mapped[str | None] = mapped_column(Text)
    # e.g. "Клиент Иванов звонил 3 дня назад, обещали перезвонить с документами..."

    # Between-call events that occurred before this call
    applied_events: Mapped[dict] = mapped_column(JSONB, default=list)
    # [{"event": "creditor_called", "impact": "client more anxious"}, ...]

    # Simulated time gap since previous call
    simulated_days_gap: Mapped[int] = mapped_column(Integer, default=1)

    # Client's starting disposition for this call (derived from previous call outcome)
    starting_emotion: Mapped[str] = mapped_column(String(50), default="cold")
    starting_trust: Mapped[int] = mapped_column(Integer, default=3)  # 1-10

    # Call outcome summary
    outcome: Mapped[str | None] = mapped_column(String(100))
    # e.g. "scheduled_meeting", "callback_requested", "deal_closed", "hangup"

    # Emotion trajectory for this call: [{"seq": 1, "state": "cold"}, {"seq": 5, "state": "curious"}, ...]
    emotion_trajectory: Mapped[dict] = mapped_column(JSONB, default=list)

    # Active factors during this call
    active_factors: Mapped[dict] = mapped_column(JSONB, default=list)
    # [{"factor": "fatigue", "intensity": 0.7}, {"factor": "time_pressure", "intensity": 0.5}]

    # Token budget usage for this call's system prompt
    system_prompt_tokens: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SessionReport(Base):
    """Auto-generated post-call / post-story report.

    Generated by a separate small LLM (via ContextBudgetManager.compress)
    after each call and after the full story completes.
    """
    __tablename__ = "session_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_stories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    call_number: Mapped[int | None] = mapped_column(Integer)

    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Types: "post_call" (after each call), "story_summary" (after all calls)

    # Report content sections (JSONB for flexibility)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Format: {
    #   "summary": "Краткое описание звонка...",
    #   "strengths": ["Хорошо обработал возражение о цене", ...],
    #   "weaknesses": ["Не проявил эмпатию при страхе клиента", ...],
    #   "missed_opportunities": ["Не использовал приём 'социальное доказательство'"],
    #   "recommendations": ["В следующем звонке сфокусируйтесь на..."],
    #   "score_breakdown": {"script": 7, "objections": 8, ...},
    #   "key_moments": [{"seq": 12, "type": "trap_fell", "detail": "..."}]
    # }

    # Scores (duplicated from TrainingSession for quick access)
    score_total: Mapped[float | None] = mapped_column(Float)

    # LLM that generated this report
    generated_by_model: Mapped[str | None] = mapped_column(String(100))
    generation_latency_ms: Mapped[int | None] = mapped_column(Integer)

    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    # True for story_summary reports

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
