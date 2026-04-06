"""Behavioral Intelligence models.

Tracks manager behavioral patterns, emotional profile, progress trends,
and personalized daily advice.

Used by:
- behavior_tracker.py — message-level signal extraction
- manager_emotion_profiler.py — confidence/stress/adaptability scoring
- progress_detector.py — trend detection, regression alerts
- daily_advice.py — personalized recommendation generation
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func, Date,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class TrendDirection(str, enum.Enum):
    improving = "improving"
    stable = "stable"
    declining = "declining"
    stagnating = "stagnating"  # No change over long period


class AlertSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


# ═══════════════════════════════════════════════════════════════════════════════
# Behavioral Snapshot — per-session behavioral signals
# ═══════════════════════════════════════════════════════════════════════════════


class BehaviorSnapshot(Base):
    """Aggregated behavioral signals from a single training/quiz session.

    Extracted after each session by behavior_tracker.track_session().
    One row per session — low cardinality, fast queries.
    """
    __tablename__ = "behavior_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    session_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "training" | "quiz" | "pvp"

    # ── Response patterns ─────────────────────────────────────────────────
    avg_response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_stddev: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Message patterns ──────────────────────────────────────────────────
    avg_message_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_message_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_message_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)

    # ── Confidence indicators ─────────────────────────────────────────────
    confidence_score: Mapped[float] = mapped_column(Float, default=50.0)
    # 0-100: based on assertive language, response consistency, legal term usage
    # High: decisive phrases, specific references, consistent length
    # Low: hedging phrases ("может быть", "не уверен"), short answers, inconsistency

    hesitation_count: Mapped[int] = mapped_column(Integer, default=0)
    # Count of hedging phrases: "может быть", "наверное", "не знаю", "думаю"

    legal_term_density: Mapped[float] = mapped_column(Float, default=0.0)
    # Percentage of messages containing legal terms (0-1)

    # ── Stress indicators ─────────────────────────────────────────────────
    stress_level: Mapped[float] = mapped_column(Float, default=30.0)
    # 0-100: based on response acceleration, short answers, emotional volatility
    # High: decreasing message length, faster/erratic timing, many pauses

    response_acceleration: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Positive = speeding up (stress), negative = slowing down (fatigue), 0 = stable

    # ── Adaptability ──────────────────────────────────────────────────────
    adaptability_score: Mapped[float] = mapped_column(Float, default=50.0)
    # 0-100: how well manager adapts to client's emotional changes
    # High: adjusts approach after negative emotion, changes strategy after trap

    emotion_response_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Did manager react appropriately to client emotion changes? (0-1)

    # ── Detailed signals (JSONB) ──────────────────────────────────────────
    signals: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Detailed per-message signals for deep analysis:
    # {
    #   "message_lengths": [45, 78, 32, ...],
    #   "response_times_ms": [3200, 1800, 5400, ...],
    #   "confidence_per_message": [0.8, 0.6, 0.9, ...],
    #   "legal_terms_used": ["банкротство", "ст. 213.4", ...],
    #   "hesitation_phrases": [{"msg": 3, "phrase": "может быть"}, ...],
    #   "emotion_reactions": [{"emotion": "hostile", "response_quality": 0.7}, ...],
    # }

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════════════════════
# Emotion Profile — aggregated emotional characteristics of the manager
# ═══════════════════════════════════════════════════════════════════════════════


class EmotionProfile(Base):
    """Manager's emotional profile based on cross-session analysis.

    Updated after each training session by manager_emotion_profiler.
    One row per user — updated in-place (not appended).
    """
    __tablename__ = "manager_emotion_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    # ── Composite scores (0-100) ──────────────────────────────────────────
    overall_confidence: Mapped[float] = mapped_column(Float, default=50.0)
    overall_stress_resistance: Mapped[float] = mapped_column(Float, default=50.0)
    overall_adaptability: Mapped[float] = mapped_column(Float, default=50.0)
    overall_empathy: Mapped[float] = mapped_column(Float, default=50.0)

    # ── OCEAN Big Five (0-100) ────────────────────────────────────────────
    # Inferred from behavioral patterns, NOT self-reported
    openness: Mapped[float] = mapped_column(Float, default=50.0)
    # High: tries different approaches, uses creative metaphors
    conscientiousness: Mapped[float] = mapped_column(Float, default=50.0)
    # High: follows script, consistent timing, thorough responses
    extraversion: Mapped[float] = mapped_column(Float, default=50.0)
    # High: long messages, fast responses, asks questions
    agreeableness: Mapped[float] = mapped_column(Float, default=50.0)
    # High: empathetic phrases, patience with hostile clients
    neuroticism: Mapped[float] = mapped_column(Float, default=50.0)
    # High: inconsistent timing, stress under pressure, short fuse

    # ── Performance under emotion types ───────────────────────────────────
    performance_under_hostility: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Score when client is hostile/aggressive (0-100)
    performance_under_stress: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Score when multiple traps activated (0-100)
    performance_with_empathy: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Score when client needs emotional support (0-100)

    # ── Archetype-specific performance ────────────────────────────────────
    archetype_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"skeptic": 72, "anxious": 45, "hostile": 38, ...}

    # ── Meta ──────────────────────────────────────────────────────────────
    sessions_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    last_updated: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════════════════════
# Progress Trend — detected trends and alerts
# ═══════════════════════════════════════════════════════════════════════════════


class ProgressTrend(Base):
    """Detected progress/regression trends for a manager.

    One row per trend detection period (daily/weekly).
    Used by progress_detector to trigger alerts for ROP.
    """
    __tablename__ = "progress_trends"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "daily" | "weekly"

    # ── Overall trend ─────────────────────────────────────────────────────
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    score_delta: Mapped[float] = mapped_column(Float, default=0.0)
    # Positive = improving, negative = declining

    # ── Per-skill trends ──────────────────────────────────────────────────
    skill_trends: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"empathy": {"direction": "improving", "delta": +5.2},
    #  "closing": {"direction": "declining", "delta": -3.1}, ...}

    # ── Behavioral trends ─────────────────────────────────────────────────
    confidence_trend: Mapped[str | None] = mapped_column(String(20), nullable=True)
    stress_trend: Mapped[str | None] = mapped_column(String(20), nullable=True)
    adaptability_trend: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── Alert ─────────────────────────────────────────────────────────────
    alert_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alert_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_seen_by_rop: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Sessions in period ────────────────────────────────────────────────
    sessions_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── Prediction ────────────────────────────────────────────────────────
    predicted_level_in_30d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_score_in_7d: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════════════════════
# Daily Advice — personalized recommendation per user per day
# ═══════════════════════════════════════════════════════════════════════════════


class DailyAdvice(Base):
    """Personalized daily recommendation for a manager.

    Generated once per day at 06:00 AM by daily_advice.generate().
    Shown on dashboard as "Совет дня".
    """
    __tablename__ = "daily_advice"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    advice_date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)

    # ── Advice content ────────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # "Работа с возражениями о цене"

    body: Mapped[str] = mapped_column(Text, nullable=False)
    # "В последних 3 сессиях вы теряли клиента на этапе обсуждения стоимости.
    #  Попробуйте сценарий 'Горячий клиент — skeptic' на средней сложности."

    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # "weak_skill" | "arena_knowledge" | "emotional_pattern" | "streak_motivation" | "general"

    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1=highest, 10=lowest

    # ── Action link ───────────────────────────────────────────────────────
    action_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # "start_training" | "start_quiz" | "view_progress" | None

    action_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"scenario_code": "in_website", "archetype": "skeptic", "difficulty": 5}
    # or {"quiz_mode": "themed", "category": "property"}

    # ── Source analysis ───────────────────────────────────────────────────
    source_analysis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # What data drove this advice:
    # {"weakest_skill": "closing", "skill_score": 35,
    #  "recent_sessions": 3, "trend": "declining",
    #  "arena_weak_category": "property"}

    # ── Tracking ──────────────────────────────────────────────────────────
    was_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    was_acted_on: Mapped[bool] = mapped_column(Boolean, default=False)
    # True if user clicked action link

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
