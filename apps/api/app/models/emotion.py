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

# Дефолтная конфигурация Mood Buffer для 25 архетипов (ТЗ-02 Блок В)
ARCHETYPE_MOOD_DEFAULTS: dict[str, dict] = {
    "skeptic":       {"threshold_pos": 65, "threshold_neg": -55, "decay": 0.08, "ema_alpha": 0.25},
    "anxious":       {"threshold_pos": 70, "threshold_neg": -45, "decay": 0.12, "ema_alpha": 0.35},
    "passive":       {"threshold_pos": 60, "threshold_neg": -50, "decay": 0.06, "ema_alpha": 0.20},
    "avoidant":      {"threshold_pos": 75, "threshold_neg": -40, "decay": 0.10, "ema_alpha": 0.30},
    "paranoid":      {"threshold_pos": 80, "threshold_neg": -35, "decay": 0.14, "ema_alpha": 0.40},
    "ashamed":       {"threshold_pos": 55, "threshold_neg": -70, "decay": 0.18, "ema_alpha": 0.45},
    "aggressive":    {"threshold_pos": 50, "threshold_neg": -60, "decay": 0.11, "ema_alpha": 0.32},
    "hostile":       {"threshold_pos": 45, "threshold_neg": -65, "decay": 0.09, "ema_alpha": 0.28},
    "blamer":        {"threshold_pos": 58, "threshold_neg": -52, "decay": 0.13, "ema_alpha": 0.38},
    "sarcastic":     {"threshold_pos": 62, "threshold_neg": -48, "decay": 0.10, "ema_alpha": 0.26},
    "know_it_all":   {"threshold_pos": 70, "threshold_neg": -42, "decay": 0.07, "ema_alpha": 0.22},
    "manipulator":   {"threshold_pos": 68, "threshold_neg": -50, "decay": 0.09, "ema_alpha": 0.24},
    "delegator":     {"threshold_pos": 72, "threshold_neg": -48, "decay": 0.08, "ema_alpha": 0.23},
    "negotiator":    {"threshold_pos": 65, "threshold_neg": -45, "decay": 0.06, "ema_alpha": 0.19},
    "shopper":       {"threshold_pos": 60, "threshold_neg": -55, "decay": 0.10, "ema_alpha": 0.29},
    "desperate":     {"threshold_pos": 40, "threshold_neg": -80, "decay": 0.20, "ema_alpha": 0.50},
    "crying":        {"threshold_pos": 35, "threshold_neg": -85, "decay": 0.22, "ema_alpha": 0.52},
    "grateful":      {"threshold_pos": 85, "threshold_neg": -25, "decay": 0.05, "ema_alpha": 0.18},
    "overwhelmed":   {"threshold_pos": 50, "threshold_neg": -75, "decay": 0.19, "ema_alpha": 0.48},
    "returner":      {"threshold_pos": 64, "threshold_neg": -56, "decay": 0.09, "ema_alpha": 0.27},
    "referred":      {"threshold_pos": 70, "threshold_neg": -48, "decay": 0.07, "ema_alpha": 0.21},
    "rushed":        {"threshold_pos": 55, "threshold_neg": -65, "decay": 0.15, "ema_alpha": 0.42},
    "couple":        {"threshold_pos": 62, "threshold_neg": -58, "decay": 0.11, "ema_alpha": 0.31},
    "lawyer_client": {"threshold_pos": 68, "threshold_neg": -52, "decay": 0.08, "ema_alpha": 0.25},
    "pragmatic":     {"threshold_pos": 66, "threshold_neg": -50, "decay": 0.07, "ema_alpha": 0.21},
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
