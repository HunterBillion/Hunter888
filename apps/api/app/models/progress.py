"""
ТЗ-06: Модели адаптивной сложности и прогрессии менеджера.

Таблицы:
  - manager_progress  — профиль прогрессии менеджера (уровень, навыки, разблокировки)
  - session_history    — история тренировочных сессий с детализацией
  - achievements       — полученные достижения
  - leaderboard_snapshots — снапшоты лидерборда
  - weekly_reports     — еженедельные отчёты
  - level_definitions  — определения 20 уровней
  - achievement_definitions — определения 35 достижений
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ──────────────────────────────────────────────────────────────────────
#  Enums
# ──────────────────────────────────────────────────────────────────────

class SessionOutcome(str, enum.Enum):
    deal = "deal"
    callback = "callback"
    hangup = "hangup"
    hostile = "hostile"
    timeout = "timeout"


class AchievementRarity(str, enum.Enum):
    common = "common"
    uncommon = "uncommon"
    rare = "rare"
    epic = "epic"
    legendary = "legendary"


class AchievementCategory(str, enum.Enum):
    results = "results"
    skills = "skills"
    challenges = "challenges"
    progression = "progression"


class SkillConfidence(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    very_high = "very_high"


class ScoreTrend(str, enum.Enum):
    improving = "improving"
    stable = "stable"
    declining = "declining"


# ──────────────────────────────────────────────────────────────────────
#  Канонические списки (для валидации)
# ──────────────────────────────────────────────────────────────────────

ALL_ARCHETYPES = [
    "skeptic", "anxious", "passive", "avoidant", "paranoid", "ashamed",
    "aggressive", "hostile", "blamer", "sarcastic",
    "manipulator", "pragmatic", "delegator", "know_it_all", "negotiator", "shopper",
    "desperate", "crying", "grateful", "overwhelmed",
    "returner", "referred", "rushed", "lawyer_client", "couple",
]

ALL_SCENARIOS = [
    "cold_ad", "cold_base", "cold_referral", "cold_partner",
    "warm_callback", "warm_noanswer", "warm_refused", "warm_dropped",
    "in_website", "in_hotline", "in_social",
    "upsell", "rescue", "couple_call", "vip_debtor",
]

EMOTION_STATES = [
    "cold", "guarded", "curious", "considering", "negotiating",
    "deal", "testing", "callback", "hostile", "hangup",
]

SKILL_NAMES = [
    "empathy", "knowledge", "objection_handling",
    "stress_resistance", "closing", "qualification",
]

DEFAULT_ARCHETYPES = ["skeptic", "anxious", "passive", "pragmatic", "desperate"]
DEFAULT_SCENARIOS = ["in_website", "cold_ad", "cold_referral"]


# ──────────────────────────────────────────────────────────────────────
#  ManagerProgress
# ──────────────────────────────────────────────────────────────────────

class ManagerProgress(Base):
    """Профиль прогрессии менеджера: уровень, XP, навыки, разблокировки."""

    __tablename__ = "manager_progress"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Прогрессия ──
    current_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )
    current_xp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    total_xp: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    total_sessions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    total_hours: Mapped[float] = mapped_column(
        Numeric(8, 2), nullable=False, default=0.0,
    )

    # ── 6 навыков (0-100) ──
    skill_empathy: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    skill_knowledge: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    skill_objection_handling: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    skill_stress_resistance: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    skill_closing: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    skill_qualification: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

    # ── Разблокировки (JSONB) ──
    unlocked_archetypes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=lambda: list(DEFAULT_ARCHETYPES),
    )
    unlocked_scenarios: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=lambda: list(DEFAULT_SCENARIOS),
    )

    # ── Аналитика ──
    weak_points: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    focus_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Streak ──
    current_deal_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_deal_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Калибровка (cold start) ──
    calibration_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calibration_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skill_confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SkillConfidence.low.value,
    )

    # ── Метаданные ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    # ── Relationships ──
    sessions: Mapped[list["SessionHistory"]] = relationship(
        back_populates="manager",
        lazy="selectin",
        foreign_keys="[SessionHistory.user_id]",
        primaryjoin="ManagerProgress.user_id == SessionHistory.user_id",
    )

    __table_args__ = (
        CheckConstraint("current_level BETWEEN 1 AND 20", name="ck_level_range"),
        CheckConstraint("current_xp >= 0", name="ck_xp_nonneg"),
        CheckConstraint("total_xp >= 0", name="ck_total_xp_nonneg"),
        CheckConstraint("skill_empathy BETWEEN 0 AND 100", name="ck_skill_empathy"),
        CheckConstraint("skill_knowledge BETWEEN 0 AND 100", name="ck_skill_knowledge"),
        CheckConstraint("skill_objection_handling BETWEEN 0 AND 100", name="ck_skill_obj"),
        CheckConstraint("skill_stress_resistance BETWEEN 0 AND 100", name="ck_skill_stress"),
        CheckConstraint("skill_closing BETWEEN 0 AND 100", name="ck_skill_closing"),
        CheckConstraint("skill_qualification BETWEEN 0 AND 100", name="ck_skill_qual"),
        Index("idx_manager_progress_level", "current_level"),
    )

    # ── Helpers ──

    def skills_dict(self) -> dict[str, int]:
        return {
            "empathy": self.skill_empathy,
            "knowledge": self.skill_knowledge,
            "objection_handling": self.skill_objection_handling,
            "stress_resistance": self.skill_stress_resistance,
            "closing": self.skill_closing,
            "qualification": self.skill_qualification,
        }

    def set_skills(self, skills: dict[str, int]) -> None:
        for name, value in skills.items():
            clamped = max(0, min(100, round(value)))
            setattr(self, f"skill_{name}", clamped)


# ──────────────────────────────────────────────────────────────────────
#  SessionHistory
# ──────────────────────────────────────────────────────────────────────

class SessionHistory(Base):
    """Результат одной тренировочной сессии с полной детализацией."""

    __tablename__ = "session_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # ── Параметры ──
    scenario_code: Mapped[str] = mapped_column(String(50), nullable=False)
    archetype_code: Mapped[str] = mapped_column(String(50), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Результат ──
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    score_total: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)

    # ── Детализация (JSONB) ──
    score_breakdown: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    # Ожидаемая структура:
    # {
    #   "script_adherence": 0-30,
    #   "objection_handling": 0-25,
    #   "communication": 0-20,
    #   "anti_patterns": -15..0,
    #   "result": 0-10,
    #   "chain_traversal": 0-10,
    #   "trap_handling": -10..+10
    # }

    # ── Эмоции и ловушки ──
    emotion_peak: Mapped[str] = mapped_column(String(30), nullable=False)
    traps_fell: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    traps_dodged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chain_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Адаптивные данные ──
    max_good_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_bad_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_difficulty_modifier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    had_comeback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mercy_activated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── XP ──
    xp_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    xp_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # ── Метаданные ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # ── Relationships ──
    manager: Mapped["ManagerProgress"] = relationship(
        back_populates="sessions",
        foreign_keys=[user_id],
        primaryjoin="SessionHistory.user_id == ManagerProgress.user_id",
    )

    __table_args__ = (
        CheckConstraint("difficulty BETWEEN 1 AND 10", name="ck_difficulty_range"),
        CheckConstraint("score_total BETWEEN 0 AND 100", name="ck_score_range"),
        CheckConstraint(
            "outcome IN ('deal','callback','hangup','hostile','timeout')",
            name="ck_outcome_values",
        ),
        CheckConstraint("duration_seconds > 0", name="ck_duration_pos"),
        CheckConstraint("traps_fell >= 0", name="ck_traps_fell_nonneg"),
        CheckConstraint("traps_dodged >= 0", name="ck_traps_dodged_nonneg"),
        CheckConstraint("xp_earned >= 0", name="ck_xp_earned_nonneg"),
        Index("idx_session_history_user_date", "user_id", "created_at"),
        Index("idx_session_history_scenario", "scenario_code", "created_at"),
        Index("idx_session_history_archetype", "archetype_code", "created_at"),
        Index("idx_session_history_outcome", "user_id", "outcome"),
        Index("idx_session_history_score", "user_id", "score_total"),
    )


# ──────────────────────────────────────────────────────────────────────
#  Achievement (полученные пользователем)
# ──────────────────────────────────────────────────────────────────────

class EarnedAchievement(Base):
    """Конкретное достижение, полученное менеджером."""

    __tablename__ = "earned_achievements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    achievement_code: Mapped[str] = mapped_column(String(50), nullable=False)
    achievement_name: Mapped[str] = mapped_column(String(100), nullable=False)
    achievement_description: Mapped[str] = mapped_column(Text, nullable=False)

    rarity: Mapped[str] = mapped_column(String(20), nullable=False)
    xp_bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category: Mapped[str] = mapped_column(String(30), nullable=False)

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "achievement_code", name="uq_achievement_user_code"),
        CheckConstraint("xp_bonus >= 0", name="ck_achievement_xp_nonneg"),
        CheckConstraint(
            "rarity IN ('common','uncommon','rare','epic','legendary')",
            name="ck_rarity_values",
        ),
        CheckConstraint(
            "category IN ('results','skills','challenges','progression')",
            name="ck_category_values",
        ),
        Index("idx_achievements_user", "user_id", "unlocked_at"),
        Index("idx_achievements_code", "user_id", "achievement_code"),
        Index("idx_achievements_rarity", "rarity"),
    )


# ──────────────────────────────────────────────────────────────────────
#  LeaderboardSnapshot
# ──────────────────────────────────────────────────────────────────────

class ProgressLeaderboardSnapshot(Base):
    """Снапшот лидерборда за период (прогрессия)."""

    __tablename__ = "progress_leaderboard_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    board_type: Mapped[str] = mapped_column(String(20), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    entries: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    total_participants: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "board_type IN ('daily','weekly','monthly','all_time')",
            name="ck_progress_board_type",
        ),
        UniqueConstraint("board_type", "period_start", "period_end", name="uq_progress_leaderboard_period"),
        Index("idx_progress_leaderboard_type_date", "board_type", "period_end"),
    )


# ──────────────────────────────────────────────────────────────────────
#  WeeklyReport
# ──────────────────────────────────────────────────────────────────────

class WeeklyReport(Base):
    """Еженедельный отчёт менеджера."""

    __tablename__ = "weekly_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    week_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sessions_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    best_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worst_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_trend: Mapped[str | None] = mapped_column(String(20), nullable=True)

    outcomes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    win_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)

    skills_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    skills_change: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    xp_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level_at_start: Mapped[int] = mapped_column(Integer, nullable=False)
    level_at_end: Mapped[int] = mapped_column(Integer, nullable=False)

    new_achievements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    weak_points: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    weekly_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_change: Mapped[int | None] = mapped_column(Integer, nullable=True)

    report_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "week_start", name="uq_weekly_report_user_week"),
        Index("idx_weekly_reports_user", "user_id", "week_start"),
    )


# ──────────────────────────────────────────────────────────────────────
#  LevelDefinition (справочник)
# ──────────────────────────────────────────────────────────────────────

class LevelDefinition(Base):
    """Определение уровня менеджера (справочник)."""

    __tablename__ = "level_definitions"

    level: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    xp_required: Mapped[int] = mapped_column(Integer, nullable=False)
    max_difficulty: Mapped[int] = mapped_column(Integer, nullable=False)

    unlocked_archetypes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unlocked_scenarios: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unlocked_mechanics: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    __table_args__ = (
        CheckConstraint("level BETWEEN 1 AND 20", name="ck_level_def_range"),
        CheckConstraint("xp_required >= 0", name="ck_xp_required_nonneg"),
        CheckConstraint("max_difficulty BETWEEN 1 AND 10", name="ck_max_diff_range"),
    )


# ──────────────────────────────────────────────────────────────────────
#  AchievementDefinition (справочник)
# ──────────────────────────────────────────────────────────────────────

class AchievementDefinition(Base):
    """Определение достижения (справочник)."""

    __tablename__ = "achievement_definitions"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    xp_bonus: Mapped[int] = mapped_column(Integer, nullable=False)
    rarity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)

    __table_args__ = (
        CheckConstraint("xp_bonus >= 0", name="ck_achdef_xp_nonneg"),
        CheckConstraint(
            "rarity IN ('common','uncommon','rare','epic','legendary')",
            name="ck_achdef_rarity",
        ),
        CheckConstraint(
            "category IN ('results','skills','challenges','progression')",
            name="ck_achdef_category",
        ),
    )
