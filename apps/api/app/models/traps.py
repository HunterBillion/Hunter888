"""
ТЗ-03: ORM-модели ловушек, цепочек возражений и каскадов Hunter888.

Таблицы:
  - trap_definitions        — 100 ловушек (8 категорий)
  - objection_chain_defs    — 30 цепочек возражений с ветвлением
  - chain_steps             — шаги цепочек (on_good / on_bad / on_skip)
  - trap_cascade_defs       — 10 каскадных цепочек
  - cascade_levels          — уровни каскадов (FELL → harder trap)
  - trap_session_log        — лог ловушек за сессию
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, CheckConstraint, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ════════════════════════════════════════════════════════════════════
#  Canonical references
# ════════════════════════════════════════════════════════════════════

TRAP_CATEGORIES = [
    "legal", "emotional", "manipulative", "expert",
    "price", "provocative", "professional", "procedural",
]

TRAP_OUTCOMES = ["fell", "dodged", "partial"]

CHAIN_STEP_TARGETS = ["DEAL", "HANGUP", "CRISIS"]  # special exit codes


# ════════════════════════════════════════════════════════════════════
#  Trap Definitions
# ════════════════════════════════════════════════════════════════════

class TrapDefinition(Base):
    """
    Определение одной ловушки.

    100 ловушек × 8 категорий, каждая с:
    - фразой клиента (+ варианты)
    - 3-уровневой детекцией (keyword → regex → LLM)
    - скоринг (penalty / bonus)
    - привязка к архетипам, профессиям, состояниям
    - каскадные связи
    """
    __tablename__ = "trap_definitions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_trap_code"),
        CheckConstraint("difficulty BETWEEN 1 AND 10", name="ck_trap_difficulty"),
        CheckConstraint("penalty <= 0", name="ck_trap_penalty"),
        CheckConstraint("bonus >= 0", name="ck_trap_bonus"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="TRAP-001 .. TRAP-100",
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
    )
    subcategory: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    difficulty: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )

    # ── Клиентские фразы ──
    client_phrase: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    client_phrase_variants: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )

    # ── Keyword detection (уровень 1, <1ms) ──
    wrong_response_keywords: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    correct_response_keywords: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )

    # ── Regex detection (уровень 2, <5ms) ──
    wrong_response_patterns: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
        comment="list of regex strings",
    )
    correct_response_patterns: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )

    # ── LLM detection (уровень 3, 500-1500ms) ──
    semantic_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.7,
    )

    # ── Scoring ──
    penalty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=-2,
    )
    bonus: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )

    # ── Examples & explanation ──
    correct_response_example: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    wrong_response_example: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    explanation: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    law_reference: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )

    # ── Привязки ──
    archetype_codes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    profession_codes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    emotion_states: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )

    # ── Cascade links ──
    triggers_trap_id: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Код ловушки, которую вызывает FELL",
    )
    blocked_by_trap_id: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Код ловушки, DODGED которой блокирует эту",
    )

    # ── Emotion effects ──
    fell_emotion_trigger: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    dodged_emotion_trigger: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True,
    )

    def __repr__(self) -> str:
        return f"<Trap {self.code}: {self.name}>"


# ════════════════════════════════════════════════════════════════════
#  Objection Chains
# ════════════════════════════════════════════════════════════════════

class ObjectionChainDef(Base):
    """
    Определение цепочки возражений (30 штук).

    Каждая цепочка — последовательность шагов с ветвлением:
    on_good → next step / DEAL
    on_bad  → fallback / HANGUP
    on_skip → optional skip
    """
    __tablename__ = "objection_chain_defs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_chain_code"),
        CheckConstraint("difficulty BETWEEN 1 AND 10", name="ck_chain_difficulty"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="CHAIN-001 .. CHAIN-030",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    archetype_codes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    scenario_types: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True,
    )

    steps: Mapped[list["ChainStep"]] = relationship(
        "ChainStep", back_populates="chain",
        order_by="ChainStep.step_order",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Chain {self.code}: {self.name}>"


class ChainStep(Base):
    """
    Один шаг цепочки возражений.

    Бранчинг:
    - on_good_step: int | 'DEAL'  → следующий шаг при успехе
    - on_bad_step:  int | 'HANGUP' | 'CRISIS' → шаг при провале
    - on_skip_step: int | null     → перескок при уклонении
    """
    __tablename__ = "chain_steps"
    __table_args__ = (
        UniqueConstraint("chain_id", "step_order", name="uq_chain_step_order"),
        Index("ix_chain_step_chain", "chain_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    chain_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("objection_chain_defs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    client_text: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Фраза клиента на этом шаге",
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="price | trust | necessity | timing | competitor | deal | emotional | conflict",
    )
    has_trap: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    trap_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="TRAP-NNN если шаг содержит ловушку",
    )
    on_good_target: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="step number | DEAL | HANGUP",
    )
    on_bad_target: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="step number | HANGUP | CRISIS",
    )
    on_skip_target: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="step number | null",
    )

    chain: Mapped["ObjectionChainDef"] = relationship(
        "ObjectionChainDef", back_populates="steps",
    )

    def __repr__(self) -> str:
        return f"<ChainStep {self.chain_id}:{self.step_order}>"


# ════════════════════════════════════════════════════════════════════
#  Trap Cascades
# ════════════════════════════════════════════════════════════════════

class TrapCascadeDef(Base):
    """
    Определение каскадной цепочки ловушек (10 штук).

    FELL на уровне N → переход на уровень N+1 (ещё сложнее).
    DODGED → каскад завершён.
    """
    __tablename__ = "trap_cascade_defs"
    __table_args__ = (
        UniqueConstraint("code", name="uq_cascade_code"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="CASCADE-001 .. CASCADE-010",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    root_trap_code: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="Код стартовой ловушки",
    )
    activation_archetypes: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    activation_states: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )

    levels: Mapped[list["CascadeLevel"]] = relationship(
        "CascadeLevel", back_populates="cascade",
        order_by="CascadeLevel.level",
        cascade="all, delete-orphan",
    )


class CascadeLevel(Base):
    """Один уровень каскада."""
    __tablename__ = "cascade_levels"
    __table_args__ = (
        UniqueConstraint("cascade_id", "level", name="uq_cascade_level"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    cascade_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("trap_cascade_defs.id", ondelete="CASCADE"),
        nullable=False,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    trap_code: Mapped[str] = mapped_column(
        String(20), nullable=False,
    )
    condition: Mapped[str] = mapped_column(
        String(20), nullable=False, default="fell",
        comment="fell | dodged | partial",
    )
    next_level: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    emotion_trigger_on_fell: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    penalty_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0,
        comment="Множитель штрафа на этом уровне",
    )

    cascade: Mapped["TrapCascadeDef"] = relationship(
        "TrapCascadeDef", back_populates="levels",
    )


# ════════════════════════════════════════════════════════════════════
#  Session Log
# ════════════════════════════════════════════════════════════════════

class TrapSessionLog(Base):
    """
    Запись ловушки/цепочки в лог за сессию.

    Одна строка = одна встреча с ловушкой.
    """
    __tablename__ = "trap_session_log"
    __table_args__ = (
        Index("ix_trap_log_session", "session_id"),
        Index("ix_trap_log_session_turn", "session_id", "turn_number"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
    )
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False,
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    trap_code: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
    )
    chain_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    cascade_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
    )
    cascade_level: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    outcome: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="fell | dodged | partial",
    )
    detection_method: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="keyword | regex | llm",
    )
    detection_confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0,
    )
    manager_response: Mapped[str] = mapped_column(
        Text, nullable=False,
    )
    score_delta: Mapped[int] = mapped_column(
        Integer, nullable=False,
    )
    emotion_trigger_fired: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
    )
    metadata_extra: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc),
    )
