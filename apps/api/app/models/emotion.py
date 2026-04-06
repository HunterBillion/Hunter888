"""
ТЗ-02: ORM-модели эмоциональной подсистемы Hunter888.

Таблицы:
  - emotion_transitions   — допустимые переходы между состояниями
  - archetype_emotion_config — Mood Buffer + матрица для каждого архетипа
  - fake_transition_defs  — определения ложных переходов (8 архетипов)
  - emotion_session_log   — лог переходов конкретной сессии
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, CheckConstraint, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ════════════════════════════════════════════════════════════════════
#  Canonical references (из models/progress.py)
# ════════════════════════════════════════════════════════════════════

EMOTION_STATES = [
    "cold", "guarded", "curious", "considering", "negotiating",
    "deal", "testing", "callback", "hostile", "hangup",
]

TRIGGER_CODES = [
    "empathy", "facts", "pressure", "bad_response", "acknowledge",
    "name_use", "motivator", "speed", "boundary", "personal",
    "hook", "challenge", "defer", "resolve_fear", "insult",
    "correct_answer", "expert_answer", "wrong_answer",
    "honest_uncertainty", "calm_response", "flexible_offer",
    "silence", "counter_aggression",
]

# Дефолтные энергии триггеров (ТЗ-02 §4)
DEFAULT_TRIGGER_ENERGY: dict[str, float] = {
    "empathy": 0.30,
    "facts": 0.25,
    "pressure": -0.40,
    "bad_response": -0.35,
    "acknowledge": 0.20,
    "name_use": 0.10,
    "motivator": 0.30,
    "speed": 0.15,
    "boundary": 0.35,
    "personal": 0.15,
    "hook": 0.50,
    "challenge": 0.00,
    "defer": 0.00,
    "resolve_fear": 0.50,
    "insult": -1.00,
    "correct_answer": 0.30,
    "expert_answer": 0.40,
    "wrong_answer": -0.60,
    "honest_uncertainty": 0.15,
    "calm_response": 0.30,
    "flexible_offer": 0.30,
    "silence": -0.20,
    "counter_aggression": -0.80,
}

# Дефолтная конфигурация Mood Buffer для 100 архетипов (DOC_01_FINAL)
# Значения: threshold_pos/neg, decay, ema_alpha — из таблиц OCEAN+MoodBuffer
ARCHETYPE_MOOD_DEFAULTS: dict[str, dict] = {
    # ── Group 1: RESISTANCE ──
    "skeptic":        {"threshold_pos": 65, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    "blamer":         {"threshold_pos": 60, "threshold_neg": -50, "decay": 0.10, "ema_alpha": 0.30},
    "sarcastic":      {"threshold_pos": 70, "threshold_neg": -45, "decay": 0.09, "ema_alpha": 0.28},
    "aggressive":     {"threshold_pos": 75, "threshold_neg": -40, "decay": 0.12, "ema_alpha": 0.35},
    "hostile":        {"threshold_pos": 85, "threshold_neg": -35, "decay": 0.14, "ema_alpha": 0.40},
    "stubborn":       {"threshold_pos": 70, "threshold_neg": -40, "decay": 0.06, "ema_alpha": 0.20},
    "conspiracy":     {"threshold_pos": 75, "threshold_neg": -50, "decay": 0.10, "ema_alpha": 0.30},
    "righteous":      {"threshold_pos": 80, "threshold_neg": -45, "decay": 0.07, "ema_alpha": 0.22},
    "litigious":      {"threshold_pos": 70, "threshold_neg": -60, "decay": 0.09, "ema_alpha": 0.28},
    "scorched_earth": {"threshold_pos": 85, "threshold_neg": -30, "decay": 0.18, "ema_alpha": 0.45},
    # ── Group 2: EMOTIONAL ──
    "grateful":       {"threshold_pos": 30, "threshold_neg": -70, "decay": 0.15, "ema_alpha": 0.40},
    "anxious":        {"threshold_pos": 55, "threshold_neg": -45, "decay": 0.12, "ema_alpha": 0.35},
    "ashamed":        {"threshold_pos": 60, "threshold_neg": -50, "decay": 0.11, "ema_alpha": 0.32},
    "overwhelmed":    {"threshold_pos": 50, "threshold_neg": -45, "decay": 0.14, "ema_alpha": 0.38},
    "desperate":      {"threshold_pos": 40, "threshold_neg": -55, "decay": 0.16, "ema_alpha": 0.42},
    "crying":         {"threshold_pos": 45, "threshold_neg": -40, "decay": 0.18, "ema_alpha": 0.48},
    "guilty":         {"threshold_pos": 50, "threshold_neg": -55, "decay": 0.12, "ema_alpha": 0.35},
    "mood_swinger":   {"threshold_pos": 35, "threshold_neg": -30, "decay": 0.22, "ema_alpha": 0.55},
    "frozen":         {"threshold_pos": 90, "threshold_neg": -25, "decay": 0.05, "ema_alpha": 0.15},
    "hysteric":       {"threshold_pos": 30, "threshold_neg": -20, "decay": 0.25, "ema_alpha": 0.60},
    # ── Group 3: CONTROL ──
    "pragmatic":      {"threshold_pos": 55, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    "shopper":        {"threshold_pos": 60, "threshold_neg": -50, "decay": 0.09, "ema_alpha": 0.28},
    "negotiator":     {"threshold_pos": 55, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    "know_it_all":    {"threshold_pos": 70, "threshold_neg": -50, "decay": 0.09, "ema_alpha": 0.28},
    "manipulator":    {"threshold_pos": 75, "threshold_neg": -70, "decay": 0.07, "ema_alpha": 0.20},
    "lawyer_client":  {"threshold_pos": 80, "threshold_neg": -65, "decay": 0.06, "ema_alpha": 0.18},
    "auditor":        {"threshold_pos": 60, "threshold_neg": -50, "decay": 0.08, "ema_alpha": 0.25},
    "strategist":     {"threshold_pos": 65, "threshold_neg": -55, "decay": 0.09, "ema_alpha": 0.28},
    "power_player":   {"threshold_pos": 55, "threshold_neg": -65, "decay": 0.10, "ema_alpha": 0.30},
    "puppet_master":  {"threshold_pos": 75, "threshold_neg": -70, "decay": 0.07, "ema_alpha": 0.20},
    # ── Group 4: AVOIDANCE ──
    "passive":        {"threshold_pos": 45, "threshold_neg": -50, "decay": 0.10, "ema_alpha": 0.30},
    "delegator":      {"threshold_pos": 50, "threshold_neg": -45, "decay": 0.11, "ema_alpha": 0.32},
    "avoidant":       {"threshold_pos": 60, "threshold_neg": -40, "decay": 0.12, "ema_alpha": 0.35},
    "paranoid":       {"threshold_pos": 80, "threshold_neg": -35, "decay": 0.14, "ema_alpha": 0.40},
    "procrastinator": {"threshold_pos": 50, "threshold_neg": -45, "decay": 0.13, "ema_alpha": 0.35},
    "ghosting":       {"threshold_pos": 65, "threshold_neg": -35, "decay": 0.18, "ema_alpha": 0.45},
    "deflector":      {"threshold_pos": 55, "threshold_neg": -45, "decay": 0.11, "ema_alpha": 0.32},
    "agreeable_ghost": {"threshold_pos": 70, "threshold_neg": -60, "decay": 0.10, "ema_alpha": 0.28},
    "fortress":       {"threshold_pos": 85, "threshold_neg": -30, "decay": 0.06, "ema_alpha": 0.18},
    "smoke_screen":   {"threshold_pos": 60, "threshold_neg": -40, "decay": 0.15, "ema_alpha": 0.40},
    # ── Group 5: SPECIAL ──
    "referred":       {"threshold_pos": 35, "threshold_neg": -65, "decay": 0.12, "ema_alpha": 0.35},
    "returner":       {"threshold_pos": 55, "threshold_neg": -55, "decay": 0.10, "ema_alpha": 0.30},
    "rushed":         {"threshold_pos": 50, "threshold_neg": -50, "decay": 0.20, "ema_alpha": 0.50},
    "couple":         {"threshold_pos": 65, "threshold_neg": -45, "decay": 0.11, "ema_alpha": 0.32},
    "elderly":        {"threshold_pos": 55, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.22},
    "young_debtor":   {"threshold_pos": 40, "threshold_neg": -40, "decay": 0.16, "ema_alpha": 0.42},
    "foreign_speaker": {"threshold_pos": 55, "threshold_neg": -50, "decay": 0.10, "ema_alpha": 0.30},
    "intermediary":   {"threshold_pos": 60, "threshold_neg": -50, "decay": 0.10, "ema_alpha": 0.28},
    "repeat_caller":  {"threshold_pos": 65, "threshold_neg": -40, "decay": 0.12, "ema_alpha": 0.35},
    "celebrity":      {"threshold_pos": 70, "threshold_neg": -60, "decay": 0.08, "ema_alpha": 0.22},
    # ── Group 6: COGNITIVE ──
    "overthinker":    {"threshold_pos": 70, "threshold_neg": -50, "decay": 0.08, "ema_alpha": 0.22},
    "concrete":       {"threshold_pos": 45, "threshold_neg": -55, "decay": 0.10, "ema_alpha": 0.30},
    "storyteller":    {"threshold_pos": 40, "threshold_neg": -50, "decay": 0.12, "ema_alpha": 0.35},
    "misinformed":    {"threshold_pos": 55, "threshold_neg": -45, "decay": 0.12, "ema_alpha": 0.35},
    "selective_listener": {"threshold_pos": 65, "threshold_neg": -50, "decay": 0.09, "ema_alpha": 0.28},
    "black_white":    {"threshold_pos": 70, "threshold_neg": -45, "decay": 0.10, "ema_alpha": 0.30},
    "memory_issues":  {"threshold_pos": 55, "threshold_neg": -45, "decay": 0.20, "ema_alpha": 0.45},
    "technical":      {"threshold_pos": 50, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    "magical_thinker": {"threshold_pos": 60, "threshold_neg": -40, "decay": 0.14, "ema_alpha": 0.38},
    "lawyer_level_2": {"threshold_pos": 75, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    # ── Group 7: SOCIAL ──
    "family_man":     {"threshold_pos": 45, "threshold_neg": -55, "decay": 0.10, "ema_alpha": 0.30},
    "influenced":     {"threshold_pos": 55, "threshold_neg": -40, "decay": 0.12, "ema_alpha": 0.35},
    "reputation_guard": {"threshold_pos": 60, "threshold_neg": -50, "decay": 0.09, "ema_alpha": 0.28},
    "community_leader": {"threshold_pos": 50, "threshold_neg": -55, "decay": 0.10, "ema_alpha": 0.30},
    "breadwinner":    {"threshold_pos": 50, "threshold_neg": -50, "decay": 0.11, "ema_alpha": 0.32},
    "divorced":       {"threshold_pos": 60, "threshold_neg": -45, "decay": 0.12, "ema_alpha": 0.35},
    "guarantor":      {"threshold_pos": 55, "threshold_neg": -45, "decay": 0.11, "ema_alpha": 0.32},
    "widow":          {"threshold_pos": 65, "threshold_neg": -30, "decay": 0.14, "ema_alpha": 0.38},
    "caregiver":      {"threshold_pos": 55, "threshold_neg": -50, "decay": 0.12, "ema_alpha": 0.35},
    "multi_debtor_family": {"threshold_pos": 65, "threshold_neg": -45, "decay": 0.10, "ema_alpha": 0.30},
    # ── Group 8: TEMPORAL ──
    "just_fired":     {"threshold_pos": 45, "threshold_neg": -45, "decay": 0.14, "ema_alpha": 0.38},
    "collector_call": {"threshold_pos": 40, "threshold_neg": -40, "decay": 0.16, "ema_alpha": 0.42},
    "court_notice":   {"threshold_pos": 45, "threshold_neg": -45, "decay": 0.14, "ema_alpha": 0.38},
    "salary_arrest":  {"threshold_pos": 40, "threshold_neg": -35, "decay": 0.16, "ema_alpha": 0.42},
    "pre_court":      {"threshold_pos": 55, "threshold_neg": -50, "decay": 0.12, "ema_alpha": 0.35},
    "post_refusal":   {"threshold_pos": 60, "threshold_neg": -45, "decay": 0.14, "ema_alpha": 0.38},
    "inheritance_trap": {"threshold_pos": 55, "threshold_neg": -50, "decay": 0.10, "ema_alpha": 0.30},
    "business_collapse": {"threshold_pos": 55, "threshold_neg": -50, "decay": 0.12, "ema_alpha": 0.35},
    "medical_crisis": {"threshold_pos": 40, "threshold_neg": -30, "decay": 0.18, "ema_alpha": 0.45},
    "criminal_risk":  {"threshold_pos": 50, "threshold_neg": -35, "decay": 0.15, "ema_alpha": 0.40},
    # ── Group 9: PROFESSIONAL ──
    "teacher":        {"threshold_pos": 45, "threshold_neg": -55, "decay": 0.10, "ema_alpha": 0.30},
    "doctor":         {"threshold_pos": 50, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    "military":       {"threshold_pos": 55, "threshold_neg": -60, "decay": 0.07, "ema_alpha": 0.22},
    "accountant":     {"threshold_pos": 50, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    "salesperson":    {"threshold_pos": 60, "threshold_neg": -55, "decay": 0.10, "ema_alpha": 0.30},
    "it_specialist":  {"threshold_pos": 50, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    "government":     {"threshold_pos": 65, "threshold_neg": -55, "decay": 0.07, "ema_alpha": 0.22},
    "journalist":     {"threshold_pos": 55, "threshold_neg": -50, "decay": 0.10, "ema_alpha": 0.30},
    "psychologist":   {"threshold_pos": 70, "threshold_neg": -60, "decay": 0.07, "ema_alpha": 0.20},
    "competitor_employee": {"threshold_pos": 75, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    # ── Group 10: COMPOUND (гибриды — расчётные значения) ──
    "aggressive_desperate":  {"threshold_pos": 80, "threshold_neg": -35, "decay": 0.11, "ema_alpha": 0.39},
    "manipulator_crying":    {"threshold_pos": 80, "threshold_neg": -35, "decay": 0.063, "ema_alpha": 0.34},
    "know_it_all_paranoid":  {"threshold_pos": 85, "threshold_neg": -30, "decay": 0.063, "ema_alpha": 0.34},
    "passive_aggressive":    {"threshold_pos": 75, "threshold_neg": -40, "decay": 0.054, "ema_alpha": 0.29},
    "couple_disagreeing":    {"threshold_pos": 80, "threshold_neg": -35, "decay": 0.099, "ema_alpha": 0.34},
    "elderly_paranoid":      {"threshold_pos": 85, "threshold_neg": -30, "decay": 0.072, "ema_alpha": 0.31},
    "hysteric_litigious":    {"threshold_pos": 75, "threshold_neg": -15, "decay": 0.081, "ema_alpha": 0.44},
    "puppet_master_lawyer":  {"threshold_pos": 85, "threshold_neg": -60, "decay": 0.054, "ema_alpha": 0.19},
    "shifting":              {"threshold_pos": 70, "threshold_neg": -40, "decay": 0.10, "ema_alpha": 0.30},
    "ultimate":              {"threshold_pos": 90, "threshold_neg": -20, "decay": 0.05, "ema_alpha": 0.25},
}

# Конфигурация Fake Transitions (ТЗ-02 Блок Г, 8 архетипов)
FAKE_TRANSITION_DEFS: list[dict] = [
    {
        "archetype_code": "manipulator",
        "real_state": "curious",
        "fake_state": "cold",
        "real_energy": 55,
        "fake_energy": -20,
        "activation_condition": "favorable_offer",
        "reveal_triggers": ["pause", "improved_offer", "direct_challenge"],
        "duration_sec": 60,
        "description": "Контролирует впечатление: делает вид, что не заинтересован, чтобы получить лучшее предложение",
    },
    {
        "archetype_code": "sarcastic",
        "real_state": "hostile",
        "fake_state": "curious",
        "real_energy": -25,
        "fake_energy": 15,
        "activation_condition": "naive_remark",
        "reveal_triggers": ["direct_comment", "observe_microexpression"],
        "duration_sec": 45,
        "description": "Маскирует раздражение весёлостью и сарказмом",
    },
    {
        "archetype_code": "know_it_all",
        "real_state": "guarded",
        "fake_state": "considering",
        "real_energy": 10,
        "fake_energy": 80,
        "activation_condition": "belief_contradiction",
        "reveal_triggers": ["specific_question", "logical_analysis"],
        "duration_sec": 90,
        "description": "Скрывает сомнения за демонстрацией уверенности",
    },
    {
        "archetype_code": "couple",
        "real_state": "guarded",
        "fake_state": "considering",
        "real_energy": -10,
        "fake_energy": 50,
        "activation_condition": "partner_a_positive",
        "reveal_triggers": ["separation", "direct_question"],
        "duration_sec": 120,
        "description": "Партнёр Б соглашается с А, но на самом деле сомневается",
    },
    {
        "archetype_code": "paranoid",
        "real_state": "hostile",
        "fake_state": "considering",
        "real_energy": -40,
        "fake_energy": 30,
        "activation_condition": "too_good_offer",
        "reveal_triggers": ["manager_vulnerability", "logic_explanation"],
        "duration_sec": 120,
        "description": "Демонстрирует ложное спокойствие, скрывая страх и подозрения",
    },
    {
        "archetype_code": "avoidant",
        "real_state": "cold",
        "fake_state": "considering",
        "real_energy": 0,
        "fake_energy": 50,
        "activation_condition": "commitment_request",
        "reveal_triggers": ["normalize_doubts", "direct_question"],
        "duration_sec": 75,
        "description": "Имитирует согласие, но на деле не готов к действию",
    },
    {
        "archetype_code": "passive",
        "real_state": "cold",
        "fake_state": "curious",
        "real_energy": 0,
        "fake_energy": 30,
        "activation_condition": "manager_initiative",
        "reveal_triggers": ["opinion_request", "contradictory_offer"],
        "duration_sec": 60,
        "description": "Зеркалит менеджера, создавая иллюзию вовлечённости",
    },
    {
        "archetype_code": "delegator",
        "real_state": "cold",
        "fake_state": "negotiating",
        "real_energy": 0,
        "fake_energy": 60,
        "activation_condition": "responsibility_offer",
        "reveal_triggers": ["responsibility_explanation", "participation_demand"],
        "duration_sec": 70,
        "description": "Маскирует нежелание участвовать, делегируя всё менеджеру",
    },
]

FAKE_TRANSITION_ARCHETYPES = [d["archetype_code"] for d in FAKE_TRANSITION_DEFS]


# ════════════════════════════════════════════════════════════════════
#  SQLAlchemy Models
# ════════════════════════════════════════════════════════════════════

class EmotionTransition(Base):
    """
    Справочник допустимых переходов между состояниями.

    Хранит: from_state → trigger → to_state + base_energy для дефолтного
    поведения (без учёта архетипа).
    """
    __tablename__ = "emotion_transitions"
    __table_args__ = (
        UniqueConstraint("from_state", "trigger_code", "to_state",
                         name="uq_emotion_transition"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    from_state: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
    )
    trigger_code: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
    )
    to_state: Mapped[str] = mapped_column(
        String(30), nullable=False,
    )
    base_energy: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ArchetypeEmotionConfig(Base):
    """
    Конфигурация Mood Buffer и energy-модификаторы триггеров
    для каждого архетипа.

    - threshold_positive / threshold_negative: пороги перехода
    - decay_coefficient: скорость затухания энергии
    - ema_alpha: вес текущего значения для EMA-сглаживания
    - trigger_modifiers: JSONB {trigger_code: float multiplier}
    - counter_gated_triggers: JSONB [{trigger, count_required, effect}]
    - initial_energy: стартовая энергия (0.0 для большинства)
    """
    __tablename__ = "archetype_emotion_configs"
    __table_args__ = (
        UniqueConstraint("archetype_code", name="uq_archetype_emotion_config"),
        CheckConstraint("threshold_positive > 0", name="ck_threshold_pos"),
        CheckConstraint("threshold_negative < 0", name="ck_threshold_neg"),
        CheckConstraint("decay_coefficient BETWEEN 0.01 AND 1.0", name="ck_decay"),
        CheckConstraint("ema_alpha BETWEEN 0.01 AND 1.0", name="ck_ema"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    archetype_code: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
    )
    initial_state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="cold",
    )
    initial_energy: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0,
    )
    threshold_positive: Mapped[float] = mapped_column(
        Float, nullable=False,
    )
    threshold_negative: Mapped[float] = mapped_column(
        Float, nullable=False,
    )
    decay_coefficient: Mapped[float] = mapped_column(
        Float, nullable=False,
    )
    ema_alpha: Mapped[float] = mapped_column(
        Float, nullable=False,
    )
    trigger_modifiers: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="{ trigger_code: multiplier }",
    )
    counter_gated_triggers: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
        comment='[{"trigger": str, "count_required": int, "target_state": str, "bonus_energy": float}]',
    )
    transition_matrix: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment='{ "from_state:trigger_code": {"to": str, "energy": float} }',
    )


class FakeTransitionDef(Base):
    """
    Определение ложного перехода для архетипа (ТЗ-02 Блок Г).

    8 архетипов с fake transitions: manipulator, sarcastic, know_it_all,
    couple, paranoid, avoidant, passive, delegator.
    """
    __tablename__ = "fake_transition_defs"
    __table_args__ = (
        UniqueConstraint("archetype_code", name="uq_fake_transition_archetype"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    archetype_code: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
    )
    real_state: Mapped[str] = mapped_column(
        String(30), nullable=False,
    )
    fake_state: Mapped[str] = mapped_column(
        String(30), nullable=False,
    )
    real_energy: Mapped[float] = mapped_column(Float, nullable=False)
    fake_energy: Mapped[float] = mapped_column(Float, nullable=False)
    activation_condition: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    reveal_triggers: Mapped[list] = mapped_column(
        JSONB, nullable=False,
    )
    duration_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class EmotionSessionLog(Base):
    """
    Запись в лог эмоциональных переходов за сессию.

    Одна строка = одна смена состояния (или попытка).
    """
    __tablename__ = "emotion_session_log"
    __table_args__ = (
        Index("ix_emotion_log_session_turn", "session_id", "turn_number"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True,
    )
    turn_number: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    from_state: Mapped[str] = mapped_column(String(30), nullable=False)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    trigger_code: Mapped[str] = mapped_column(String(50), nullable=False)
    energy_delta: Mapped[float] = mapped_column(Float, nullable=False)
    energy_before: Mapped[float] = mapped_column(Float, nullable=False)
    energy_after: Mapped[float] = mapped_column(Float, nullable=False)
    energy_smoothed: Mapped[float] = mapped_column(Float, nullable=False)
    is_fake: Mapped[bool] = mapped_column(Boolean, default=False)
    fake_real_state: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True,
    )
    mood_buffer_zone: Mapped[str] = mapped_column(
        String(20), nullable=False, default="neutral",
        comment="positive | negative | neutral",
    )
    metadata_extra: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow,
    )
    # DOC_08: Emotion v6 extensions (all nullable for backward compat)
    intensity_level: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    intensity_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    compound_emotion: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    micro_expression: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
