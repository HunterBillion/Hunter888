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
    # Group 1: RESISTANCE
    "skeptic", "blamer", "sarcastic", "aggressive", "hostile",
    "stubborn", "conspiracy", "righteous", "litigious", "scorched_earth",
    # Group 2: EMOTIONAL
    "grateful", "anxious", "ashamed", "overwhelmed", "desperate",
    "crying", "guilty", "mood_swinger", "frozen", "hysteric",
    # Group 3: CONTROL
    "pragmatic", "shopper", "negotiator", "know_it_all", "manipulator",
    "lawyer_client", "auditor", "strategist", "power_player", "puppet_master",
    # Group 4: AVOIDANCE
    "passive", "delegator", "avoidant", "paranoid",
    "procrastinator", "ghosting", "deflector", "agreeable_ghost", "fortress", "smoke_screen",
    # Group 5: SPECIAL
    "referred", "returner", "rushed", "couple",
    "elderly", "young_debtor", "foreign_speaker", "intermediary", "repeat_caller", "celebrity",
    # Group 6: COGNITIVE
    "overthinker", "concrete", "storyteller", "misinformed", "selective_listener",
    "black_white", "memory_issues", "technical", "magical_thinker", "lawyer_level_2",
    # Group 7: SOCIAL
    "family_man", "influenced", "reputation_guard", "community_leader", "breadwinner",
    "divorced", "guarantor", "widow", "caregiver", "multi_debtor_family",
    # Group 8: TEMPORAL
    "just_fired", "collector_call", "court_notice", "salary_arrest", "pre_court",
    "post_refusal", "inheritance_trap", "business_collapse", "medical_crisis", "criminal_risk",
    # Group 9: PROFESSIONAL
    "teacher", "doctor", "military", "accountant", "salesperson",
    "it_specialist", "government", "journalist", "psychologist", "competitor_employee",
    # Group 10: COMPOUND
    "aggressive_desperate", "manipulator_crying", "know_it_all_paranoid", "passive_aggressive",
    "couple_disagreeing", "elderly_paranoid", "hysteric_litigious", "puppet_master_lawyer",
    "shifting", "ultimate",
]

ALL_SCENARIOS = [
    # Group A: Outbound Cold (10)
    "cold_ad", "cold_referral", "cold_social", "cold_database", "cold_base",
    "cold_partner", "cold_premium", "cold_event", "cold_expired", "cold_insurance",
    # Group B: Outbound Warm (10)
    "warm_callback", "warm_noanswer", "warm_refused", "warm_dropped",
    "warm_repeat", "warm_webinar", "warm_vip", "warm_ghosted", "warm_complaint", "warm_competitor",
    # Group C: Inbound (8)
    "in_website", "in_hotline", "in_social", "in_chatbot",
    "in_partner", "in_complaint", "in_urgent", "in_corporate",
    # Group D: Special (12)
    "special_ghosted", "special_urgent", "special_guarantor", "special_couple",
    "upsell", "rescue", "special_inheritance", "vip_debtor",
    "special_psychologist", "special_vip", "special_medical", "special_boss",
    # Group E: Follow-up (5)
    "follow_up_first", "follow_up_second", "follow_up_third", "follow_up_rescue", "follow_up_memory",
    # Group F: Crisis (5)
    "crisis_collector", "crisis_pre_court", "crisis_business", "crisis_criminal", "crisis_full",
    # Group G: Compliance (5)
    "compliance_basic", "compliance_docs", "compliance_legal", "compliance_advanced", "compliance_full",
    # Group H: Multi-party (5)
    "multi_party_basic", "multi_party_lawyer", "multi_party_creditors", "multi_party_family", "multi_party_full",
]

EMOTION_STATES = [
    "cold", "guarded", "curious", "considering", "negotiating",
    "deal", "testing", "callback", "hostile", "hangup",
]

SKILL_NAMES = [
    "empathy", "knowledge", "objection_handling",
    "stress_resistance", "closing", "qualification",
    "time_management", "adaptation", "legal_knowledge", "rapport_building",
]

DEFAULT_ARCHETYPES = ["skeptic", "anxious", "passive", "pragmatic", "desperate", "concrete", "procrastinator"]
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
    # ── 4 new skills (DOC_06: 6 → 10) ──
    skill_time_management: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    skill_adaptation: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    skill_legal_knowledge: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    skill_rapport_building: Mapped[int] = mapped_column(Integer, nullable=False, default=50)

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

    # ── Perfect Score Streak (3+ sessions with score >80) ──
    perfect_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_perfect_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Arena Knowledge Streak ──
    arena_answer_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arena_best_answer_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arena_daily_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arena_last_quiz_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Чекпоинты (DOC_04) ──
    checkpoints_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level_checkpoints_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Калибровка (cold start) ──
    calibration_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calibration_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skill_confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SkillConfidence.low.value,
    )

    # ── Hunter Score (DOC_14) ──
    hunter_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    hunter_score_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Prestige (DOC_15: post-level-20 progression) ──
    prestige_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-5
    prestige_xp_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)  # 1.0-1.5

    # ── Season Pass (DOC_15) ──
    season_pass_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-30
    season_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Arena Points (DOC_13) ──
    arena_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arena_points_last_month: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    arena_points_total_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Daily Drill (habit loop) ──
    last_drill_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    drill_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_drill_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_drills: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Weekly League ──
    league_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-4

    # ── Метаданные ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    # ── Relationships ──
    # lazy="select" (default) — load on explicit access only.
    # Was "selectin" which eagerly loads ALL sessions (potentially 1000+) on every
    # ManagerProgress query, causing major performance issues.
    sessions: Mapped[list["SessionHistory"]] = relationship(
        back_populates="manager",
        lazy="select",
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
            "time_management": self.skill_time_management,
            "adaptation": self.skill_adaptation,
            "legal_knowledge": self.skill_legal_knowledge,
            "rapport_building": self.skill_rapport_building,
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
    """Определение достижения (справочник, DOC_07: 140 ачивок, 8 категорий)."""

    __tablename__ = "achievement_definitions"

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    xp_bonus: Mapped[int] = mapped_column(Integer, nullable=False)
    rarity: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    # DOC_07 extensions
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)               # hint shown before unlock (secrets)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_anti: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # anti-achievement (0 XP, recommendation)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)       # improvement tip for anti-achievements

    __table_args__ = (
        CheckConstraint("xp_bonus >= 0", name="ck_achdef_xp_nonneg"),
        CheckConstraint(
            "rarity IN ('common','uncommon','rare','epic','legendary')",
            name="ck_achdef_rarity",
        ),
        CheckConstraint(
            "category IN ('results','skills','challenges','progression','arena','social','narrative','secret')",
            name="ck_achdef_category_v2",
        ),
        Index("idx_achievement_definitions_category", "category"),
        Index("idx_achievement_definitions_rarity", "rarity"),
    )


# ──────────────────────────────────────────────────────────────────────
#  GoalCompletionLog — prevent duplicate XP awards for daily/weekly goals
# ──────────────────────────────────────────────────────────────────────

class GoalCompletionLog(Base):
    """Tracks which goals have been awarded XP to prevent duplicates."""
    __tablename__ = "goal_completion_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    goal_id: Mapped[str] = mapped_column(String(50), nullable=False)
    period_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    xp_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "goal_id", "period_date", name="uq_goal_completion_user_goal_period"),
    )


# ──────────────────────────────────────────────────────────────────────
#  StreakFreeze — streak protection item (purchasable for AP)
# ──────────────────────────────────────────────────────────────────────

class StreakFreeze(Base):
    """Streak freeze item: protects drill streak from breaking on 1 missed day."""
    __tablename__ = "streak_freezes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    month_year: Mapped[str] = mapped_column(
        String(7), nullable=False,  # "2026-04" format for monthly cap
    )
