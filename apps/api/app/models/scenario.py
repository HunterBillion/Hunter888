"""Scenario system v2: 15 call scenario types with conversation stages.

Replaces the old 4-type ScenarioType with a full 15-code ScenarioCode enum,
adds ScenarioTemplate (archetype weights, stages, scoring) and ConversationStageModel.
Keeps backward-compatible Scenario model for existing sessions.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ─── Canonical enums ────────────────────────────────────────────────────────


class ScenarioCode(str, enum.Enum):
    """60 canonical scenario codes (DOC_05: 8 groups)."""

    # ── Group A: Outbound Cold (10) ──
    cold_ad = "cold_ad"
    cold_referral = "cold_referral"
    cold_social = "cold_social"
    cold_database = "cold_database"
    cold_base = "cold_base"
    cold_partner = "cold_partner"
    cold_premium = "cold_premium"
    cold_event = "cold_event"
    cold_expired = "cold_expired"
    cold_insurance = "cold_insurance"
    # ── Group B: Outbound Warm (10) ──
    warm_callback = "warm_callback"
    warm_noanswer = "warm_noanswer"
    warm_refused = "warm_refused"
    warm_dropped = "warm_dropped"
    warm_repeat = "warm_repeat"
    warm_webinar = "warm_webinar"
    warm_vip = "warm_vip"
    warm_ghosted = "warm_ghosted"
    warm_complaint = "warm_complaint"
    warm_competitor = "warm_competitor"
    # ── Group C: Inbound (8) ──
    in_website = "in_website"
    in_hotline = "in_hotline"
    in_social = "in_social"
    in_chatbot = "in_chatbot"
    in_partner = "in_partner"
    in_complaint = "in_complaint"
    in_urgent = "in_urgent"
    in_corporate = "in_corporate"
    # ── Group D: Special (12) ──
    special_ghosted = "special_ghosted"
    special_urgent = "special_urgent"
    special_guarantor = "special_guarantor"
    special_couple = "special_couple"      # was: couple_call
    upsell = "upsell"
    rescue = "rescue"
    special_inheritance = "special_inheritance"
    vip_debtor = "vip_debtor"
    special_psychologist = "special_psychologist"
    special_vip = "special_vip"
    special_medical = "special_medical"
    special_boss = "special_boss"
    # ── Group E: Follow-up (5) ──
    follow_up_first = "follow_up_first"
    follow_up_second = "follow_up_second"
    follow_up_third = "follow_up_third"
    follow_up_rescue = "follow_up_rescue"
    follow_up_memory = "follow_up_memory"
    # ── Group F: Crisis (5) ──
    crisis_collector = "crisis_collector"
    crisis_pre_court = "crisis_pre_court"
    crisis_business = "crisis_business"
    crisis_criminal = "crisis_criminal"
    crisis_full = "crisis_full"
    # ── Group G: Compliance (5) ──
    compliance_basic = "compliance_basic"
    compliance_docs = "compliance_docs"
    compliance_legal = "compliance_legal"
    compliance_advanced = "compliance_advanced"
    compliance_full = "compliance_full"
    # ── Group H: Multi-party (5) ──
    multi_party_basic = "multi_party_basic"
    multi_party_lawyer = "multi_party_lawyer"
    multi_party_creditors = "multi_party_creditors"
    multi_party_family = "multi_party_family"
    multi_party_full = "multi_party_full"


class FunnelStage(str, enum.Enum):
    lead = "lead"
    qualification = "qualification"
    meeting = "meeting"
    close = "close"
    retention = "retention"
    upsell = "upsell"


class CallerType(str, enum.Enum):
    manager = "manager"
    client = "client"
    both = "both"


class AwarenessLevel(str, enum.Enum):
    zero = "zero"
    low = "low"
    medium = "medium"
    high = "high"
    mixed = "mixed"


class MotivationLevel(str, enum.Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"
    very_high = "very_high"
    negative = "negative"
    neutral = "neutral"
    mixed = "mixed"


class TargetOutcome(str, enum.Enum):
    meeting = "meeting"
    callback = "callback"
    payment = "payment"
    qualification = "qualification"
    retention = "retention"
    upsell = "upsell"


# ─── Legacy enum (kept for backward compatibility) ──────────────────────────


class ScenarioType(str, enum.Enum):
    cold_call = "cold_call"
    warm_call = "warm_call"
    objection_handling = "objection_handling"
    consultation = "consultation"


# ─── Models ─────────────────────────────────────────────────────────────────


class ScenarioTemplate(Base):
    """Full scenario specification with archetype weights, stages, and scoring.

    This is the new v2 scenario model that replaces the simple Scenario for
    roleplay session configuration. Each template defines:
    - Call context (who calls, funnel stage, awareness)
    - Archetype probability weights (25 archetypes, sum = 100)
    - Conversation stages with goals and mistakes
    - Scoring modifiers
    - Trap and chain configuration
    """

    __tablename__ = "scenario_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    group_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="custom"
    )  # A/B/C/D

    # ── Call context ──
    who_calls: Mapped[str] = mapped_column(String(20), nullable=False, default="manager")
    funnel_stage: Mapped[str] = mapped_column(String(50), nullable=False, default="lead")
    prior_contact: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── Initial conditions ──
    initial_emotion: Mapped[str] = mapped_column(
        String(50), nullable=False, default="cold"
    )
    initial_emotion_variants: Mapped[dict] = mapped_column(
        JSONB, default=dict
    )  # {"cold": 0.5, "guarded": 0.3, "hostile": 0.2}
    client_awareness: Mapped[str] = mapped_column(
        String(20), nullable=False, default="zero"
    )
    client_motivation: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none"
    )

    # ── Duration ──
    typical_duration_minutes: Mapped[int] = mapped_column(Integer, default=8)
    max_duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    typical_reply_count_min: Mapped[int] = mapped_column(Integer, default=6)
    typical_reply_count_max: Mapped[int] = mapped_column(Integer, default=15)

    # ── Target ──
    target_outcome: Mapped[str] = mapped_column(
        String(50), nullable=False, default="meeting"
    )
    difficulty: Mapped[int] = mapped_column(Integer, default=5)  # 1-10

    # ── Archetype weights (25 entries, sum ≈ 100) ──
    archetype_weights: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )  # {"skeptic": 18.0, "avoidant": 14.0, ...}

    # ── Lead sources ──
    lead_sources: Mapped[dict] = mapped_column(
        JSONB, default=list
    )  # ["yandex_direct", "vk_target", ...]

    # ── Stages (ordered list of stage dicts) ──
    stages: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=list
    )
    # Each stage: {
    #   "order": 1, "name": "Приветствие", "description": "...",
    #   "manager_goals": [...], "manager_mistakes": [...],
    #   "expected_emotion_range": ["cold", "guarded"],
    #   "emotion_red_flag": "hostile",
    #   "duration_min": 1, "duration_max": 2,
    #   "required": true
    # }

    # ── Chains and traps ──
    recommended_chains: Mapped[dict] = mapped_column(
        JSONB, default=list
    )  # [{"code": "proof_chain", "name": "..."}, ...]
    trap_pool_categories: Mapped[dict] = mapped_column(
        JSONB, default=list
    )  # ["price", "emotional", ...]
    traps_count_min: Mapped[int] = mapped_column(Integer, default=1)
    traps_count_max: Mapped[int] = mapped_column(Integer, default=2)
    cascades_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── Scoring modifiers ──
    scoring_modifiers: Mapped[dict] = mapped_column(
        JSONB, default=list
    )
    # [{"param": "empathy", "delta": +3, "condition": "..."}, ...]

    # ── Awareness prompt injection ──
    awareness_prompt: Mapped[str | None] = mapped_column(Text)
    stage_skip_reactions: Mapped[dict] = mapped_column(
        JSONB, default=dict
    )
    # {"greeting_skip": "А вы кто вообще?", "qualification_skip": "...", ...}

    # ── Client prompt injection template ──
    client_prompt_template: Mapped[str | None] = mapped_column(Text)

    # ── Meta ──
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Scenario(Base):
    """Original Scenario model — kept for backward compatibility.

    Training sessions reference this table. ScenarioTemplate is used for
    generating new session configurations.
    """

    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_type: Mapped[ScenarioType] = mapped_column(
        Enum(ScenarioType), nullable=False
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("characters.id", ondelete="SET NULL"), nullable=False, index=True
    )
    script_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scripts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Link to v2 template (nullable for legacy scenarios)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenario_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    difficulty: Mapped[int] = mapped_column(Integer, default=5)
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
