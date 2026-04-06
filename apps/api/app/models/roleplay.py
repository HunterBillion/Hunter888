"""Roleplay system v2 models: client profiles, professions, emotion profiles, traps, objection chains.

Extended with:
- 25 canonical archetypes
- 8 trap categories with subcategories
- 3-level detection support (keyword/regex/LLM)
- Cascade traps (triggers_trap_id / blocked_by_trap_id)
- Emotion engine integration (fell_emotion_trigger / dodged_emotion_trigger)
- Branching objection chains with archetype/scenario filtering
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ArchetypeCode(str, enum.Enum):
    """100 canonical client archetypes: 10 groups × 10 archetypes."""
    # ── Group 1: RESISTANCE (Сопротивление) ──
    skeptic = "skeptic"
    blamer = "blamer"
    sarcastic = "sarcastic"
    aggressive = "aggressive"
    hostile = "hostile"
    stubborn = "stubborn"
    conspiracy = "conspiracy"
    righteous = "righteous"
    litigious = "litigious"
    scorched_earth = "scorched_earth"
    # ── Group 2: EMOTIONAL (Эмоциональные) ──
    grateful = "grateful"
    anxious = "anxious"
    ashamed = "ashamed"
    overwhelmed = "overwhelmed"
    desperate = "desperate"
    crying = "crying"
    guilty = "guilty"
    mood_swinger = "mood_swinger"
    frozen = "frozen"
    hysteric = "hysteric"
    # ── Group 3: CONTROL (Контроль) ──
    pragmatic = "pragmatic"
    shopper = "shopper"
    negotiator = "negotiator"
    know_it_all = "know_it_all"
    manipulator = "manipulator"
    lawyer_client = "lawyer_client"
    auditor = "auditor"
    strategist = "strategist"
    power_player = "power_player"
    puppet_master = "puppet_master"
    # ── Group 4: AVOIDANCE (Избегание) ──
    passive = "passive"
    delegator = "delegator"
    avoidant = "avoidant"
    paranoid = "paranoid"
    procrastinator = "procrastinator"
    ghosting = "ghosting"
    deflector = "deflector"
    agreeable_ghost = "agreeable_ghost"
    fortress = "fortress"
    smoke_screen = "smoke_screen"
    # ── Group 5: SPECIAL (Особые) ──
    referred = "referred"
    returner = "returner"
    rushed = "rushed"
    couple = "couple"
    elderly = "elderly"
    young_debtor = "young_debtor"
    foreign_speaker = "foreign_speaker"
    intermediary = "intermediary"
    repeat_caller = "repeat_caller"
    celebrity = "celebrity"
    # ── Group 6: COGNITIVE (Когнитивные) ──
    overthinker = "overthinker"
    concrete = "concrete"
    storyteller = "storyteller"
    misinformed = "misinformed"
    selective_listener = "selective_listener"
    black_white = "black_white"
    memory_issues = "memory_issues"
    technical = "technical"
    magical_thinker = "magical_thinker"
    lawyer_level_2 = "lawyer_level_2"
    # ── Group 7: SOCIAL (Социальные) ──
    family_man = "family_man"
    influenced = "influenced"
    reputation_guard = "reputation_guard"
    community_leader = "community_leader"
    breadwinner = "breadwinner"
    divorced = "divorced"
    guarantor = "guarantor"
    widow = "widow"
    caregiver = "caregiver"
    multi_debtor_family = "multi_debtor_family"
    # ── Group 8: TEMPORAL (Ситуативные) ──
    just_fired = "just_fired"
    collector_call = "collector_call"
    court_notice = "court_notice"
    salary_arrest = "salary_arrest"
    pre_court = "pre_court"
    post_refusal = "post_refusal"
    inheritance_trap = "inheritance_trap"
    business_collapse = "business_collapse"
    medical_crisis = "medical_crisis"
    criminal_risk = "criminal_risk"
    # ── Group 9: PROFESSIONAL (Профессиональные) ──
    teacher = "teacher"
    doctor = "doctor"
    military = "military"
    accountant = "accountant"
    salesperson = "salesperson"
    it_specialist = "it_specialist"
    government = "government"
    journalist = "journalist"
    psychologist = "psychologist"
    competitor_employee = "competitor_employee"
    # ── Group 10: COMPOUND (Гибриды) ──
    aggressive_desperate = "aggressive_desperate"
    manipulator_crying = "manipulator_crying"
    know_it_all_paranoid = "know_it_all_paranoid"
    passive_aggressive = "passive_aggressive"
    couple_disagreeing = "couple_disagreeing"
    elderly_paranoid = "elderly_paranoid"
    hysteric_litigious = "hysteric_litigious"
    puppet_master_lawyer = "puppet_master_lawyer"
    shifting = "shifting"
    ultimate = "ultimate"


class TrapCategory(str, enum.Enum):
    """10 trap categories: 8 standard (ТЗ-03) + 2 v2 narrative (ТЗ-03 v2)."""
    # v1 standard categories (100 static traps)
    legal = "legal"
    emotional = "emotional"
    manipulative = "manipulative"
    expert = "expert"
    price = "price"
    provocative = "provocative"
    professional = "professional"
    procedural = "procedural"
    # v2 narrative categories (dynamic traps generated from ClientStory)
    narrative = "narrative"          # memory_check + promise_check + consistency_check
    human_factor = "human_factor"    # patience_check + empathy_check + flattery_check


class EmotionState(str, enum.Enum):
    """10 emotion states in the emotion engine."""
    cold = "cold"
    guarded = "guarded"
    curious = "curious"
    considering = "considering"
    negotiating = "negotiating"
    deal = "deal"
    testing = "testing"
    callback = "callback"
    hostile = "hostile"
    hangup = "hangup"


class ScenarioType(str, enum.Enum):
    """15 canonical scenarios."""
    cold_ad = "cold_ad"
    cold_base = "cold_base"
    cold_referral = "cold_referral"
    cold_partner = "cold_partner"
    warm_callback = "warm_callback"
    warm_noanswer = "warm_noanswer"
    warm_refused = "warm_refused"
    warm_dropped = "warm_dropped"
    in_website = "in_website"
    in_hotline = "in_hotline"
    in_social = "in_social"
    upsell = "upsell"
    rescue = "rescue"
    couple_call = "couple_call"
    vip_debtor = "vip_debtor"


class DetectionLevel(str, enum.Enum):
    """3-level trap detection: keyword (<1ms), regex (<5ms), LLM (500-1500ms)."""
    keyword = "keyword"    # difficulty 1-3
    regex = "regex"        # difficulty 4-7
    llm = "llm"            # difficulty 8-10


class LeadSource(str, enum.Enum):
    cold_base = "cold_base"
    website_form = "website_form"
    referral = "referral"
    social_media = "social_media"
    repeat_call = "repeat_call"
    incoming = "incoming"
    partner = "partner"
    chatbot = "chatbot"
    webinar = "webinar"
    churned = "churned"


class ProfessionCategory(str, enum.Enum):
    budget = "budget"
    government = "government"
    military = "military"
    pensioner = "pensioner"
    entrepreneur = "entrepreneur"
    worker = "worker"
    it_office = "it_office"
    trade_service = "trade_service"
    homemaker = "homemaker"
    special = "special"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ProfessionProfile(Base):
    __tablename__ = "profession_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[ProfessionCategory] = mapped_column(Enum(ProfessionCategory), nullable=False)
    typical_debt_min: Mapped[int] = mapped_column(Integer, default=100000)
    typical_debt_max: Mapped[int] = mapped_column(Integer, default=1000000)
    legal_literacy: Mapped[int] = mapped_column(Integer, default=2)  # 1-10
    vocabulary_level: Mapped[str] = mapped_column(String(50), default="simple")  # simple|standard|professional|legal
    specific_fears: Mapped[list] = mapped_column(JSONB, default=list)  # list of fear codes
    specific_objections: Mapped[list] = mapped_column(JSONB, default=list)  # list of objection templates
    speech_patterns: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"style": "...", "markers": [...]}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    client_profiles: Mapped[list["ClientProfile"]] = relationship(back_populates="profession")


class ArchetypeEmotionProfile(Base):
    """Per-archetype emotion configuration: transition matrix, rollback triggers, fake transitions.

    Renamed from EmotionProfile to avoid conflict with behavior.EmotionProfile
    (manager OCEAN profile). Table name unchanged for backward compatibility.
    """
    __tablename__ = "emotion_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archetype_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    transition_matrix: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Format: {"cold": {"empathy": 0, "facts": 1, "pressure": -1, ...}, "guarded": {...}, ...}
    rollback_triggers: Mapped[list] = mapped_column(JSONB, default=list)
    rollback_severity: Mapped[int] = mapped_column(Integer, default=1)  # How many phases to rollback
    breaking_point: Mapped[dict | None] = mapped_column(JSONB)  # {"trigger": "...", "jump": 2}
    initial_state: Mapped[str] = mapped_column(String(50), default="cold")
    max_state_first_call: Mapped[str] = mapped_column(String(50), default="deal")
    fake_transitions: Mapped[bool] = mapped_column(Boolean, default=False)  # Manipulator can fake deal
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Trap(Base):
    """Extended trap model with 3-level detection, cascades, and emotion integration.

    Detection levels by difficulty:
    - 1-3: keyword matching only (wrong_response_keywords / correct_response_keywords)
    - 4-7: regex patterns (wrong_response_patterns / correct_response_patterns)
    - 8-10: LLM-based semantic analysis (uses all fields + explanation for context)

    Cascade support:
    - triggers_trap_id: if manager FELL on this trap, activate the linked harder trap
    - blocked_by_trap_id: this trap only activates if the blocking trap was DODGED

    Emotion integration:
    - fell_emotion_trigger: emotion state change when manager falls for trap
    - dodged_emotion_trigger: emotion state change when manager dodges trap
    """
    __tablename__ = "traps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # --- Identity ---
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)  # TrapCategory value
    subcategory: Mapped[str | None] = mapped_column(String(100))  # e.g. "property_hide", "court_fear"
    difficulty: Mapped[int] = mapped_column(Integer, default=5)  # 1-10
    detection_level: Mapped[str] = mapped_column(
        String(20), default="keyword"
    )  # keyword|regex|llm — derived from difficulty

    # --- Client phrases ---
    client_phrase: Mapped[str] = mapped_column(Text, nullable=False)  # Primary phrase
    client_phrase_variants: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # 2-3 rephrasings for variety

    # --- Wrong response detection ---
    wrong_response_keywords: Mapped[list] = mapped_column(JSONB, default=list)
    wrong_response_patterns: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # Regex patterns for level 2+ detection
    wrong_response_example: Mapped[str | None] = mapped_column(Text)  # Example of wrong answer

    # --- Correct response detection ---
    correct_response_keywords: Mapped[list] = mapped_column(JSONB, default=list)
    correct_response_patterns: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # Regex patterns for level 2+ detection
    correct_response_example: Mapped[str | None] = mapped_column(Text)  # Example of correct answer

    # --- Scoring ---
    penalty: Mapped[int] = mapped_column(Integer, default=-3)  # Score for FELL (-3 to -5)
    bonus: Mapped[int] = mapped_column(Integer, default=2)  # Score for DODGED (+2 to +3)

    # --- Educational ---
    explanation: Mapped[str | None] = mapped_column(Text)  # Why this response is wrong/right
    law_reference: Mapped[str | None] = mapped_column(Text)  # References to 127-ФЗ articles

    # --- Filtering ---
    archetype_codes: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # Which archetypes use this trap: ["skeptic", "manipulator"]
    profession_codes: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # Which professions trigger this trap: ["lawyer_client", "entrepreneur"]
    emotion_states: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # Active in which emotion states: ["cold", "guarded", "hostile"]

    # --- Cascade links ---
    triggers_trap_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traps.id", ondelete="SET NULL"), nullable=True, index=True
    )  # On FELL → activate this harder trap
    blocked_by_trap_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traps.id", ondelete="SET NULL"), nullable=True, index=True
    )  # Only activate if this trap was DODGED

    # --- Emotion engine integration ---
    fell_emotion_trigger: Mapped[str | None] = mapped_column(
        String(50)
    )  # Emotion state to transition to on FELL (e.g. "hostile")
    dodged_emotion_trigger: Mapped[str | None] = mapped_column(
        String(50)
    )  # Emotion state to transition to on DODGED (e.g. "considering")

    # --- Meta ---
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # --- Relationships (self-referential for cascades) ---
    triggered_trap = relationship(
        "Trap", remote_side="Trap.id", foreign_keys=[triggers_trap_id],
        backref=backref("triggered_by", uselist=False),
    )
    blocking_trap = relationship(
        "Trap", remote_side="Trap.id", foreign_keys=[blocked_by_trap_id],
        backref=backref("blocks", uselist=False),
    )


class ObjectionChain(Base):
    """Extended objection chain with branching, archetype/scenario filtering, and scoring.

    Steps format (JSONB):
    [
        {
            "order": 0,
            "text": "Сколько стоит? 150К?! Дорого!",
            "category": "price",
            "trap": false,
            "trap_id": null,
            "on_good_response": 1,     # go to step 1
            "on_bad_response": "fail",  # chain fails
            "on_skip": 2,              # skip to step 2
            "min_score_to_advance": 3   # minimum response quality to advance
        },
        ...
    ]
    """
    __tablename__ = "objection_chains"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=5)
    steps: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Extended step format with branching — see docstring

    # --- Filtering ---
    archetype_codes: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # Which archetypes use this chain: ["skeptic", "pragmatic"]
    scenario_types: Mapped[list] = mapped_column(
        JSONB, default=list
    )  # Which scenarios use this chain: ["cold_base", "warm_callback"]

    # --- Scoring config ---
    step_bonus: Mapped[int] = mapped_column(Integer, default=2)  # Points per completed step
    full_chain_bonus: Mapped[int] = mapped_column(Integer, default=5)  # Bonus for completing all steps
    max_score: Mapped[int] = mapped_column(Integer, default=10)  # Cap for chain contribution

    # --- Meta ---
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    client_profiles: Mapped[list["ClientProfile"]] = relationship(back_populates="chain")


class TrapCascade(Base):
    """Cascade definition: a named tree of escalating traps.

    A cascade groups 3-4 traps into an escalating sequence. When a manager
    FELL on level N, the cascade auto-activates level N+1.

    The actual trap linking is done via Trap.triggers_trap_id, but this model
    provides metadata and a convenient way to manage cascade trees.
    """
    __tablename__ = "trap_cascades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    theme: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "property", "relatives", "fear"
    difficulty_range: Mapped[str] = mapped_column(String(20), default="3-8")  # "min-max"
    levels: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Format: [
    #   {"level": 1, "trap_id": "uuid", "name": "...", "on_fell": "next", "on_dodged": "stop"},
    #   {"level": 2, "trap_id": "uuid", "name": "...", "on_fell": "next", "on_dodged": "stop"},
    #   {"level": 3, "trap_id": "uuid", "name": "...", "on_fell": "stop", "on_dodged": "stop"},
    # ]
    emotion_escalation: Mapped[dict | None] = mapped_column(JSONB)
    # Format: {"level_1_fell": "guarded", "level_2_fell": "hostile", "level_3_fell": "hangup"}
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientProfile(Base):
    __tablename__ = "client_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Identity
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(20), default="male")
    city: Mapped[str] = mapped_column(String(200), default="Москва")
    # Archetype + Profession
    archetype_code: Mapped[str] = mapped_column(String(50), nullable=False)
    profession_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profession_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    education_level: Mapped[str] = mapped_column(String(50), default="средне-специальное")
    legal_literacy: Mapped[int] = mapped_column(Integer, default=2)
    # Finances
    total_debt: Mapped[int] = mapped_column(Integer, default=500000)
    creditors: Mapped[list] = mapped_column(JSONB, default=list)  # [{"name": "Сбербанк", "amount": 1400000}]
    income: Mapped[int | None] = mapped_column(Integer)
    income_type: Mapped[str] = mapped_column(String(50), default="official")  # official|gray|mixed|none
    property_list: Mapped[list] = mapped_column(JSONB, default=list)  # [{"type": "квартира", "status": "единственная"}]
    # Psychology
    fears: Mapped[list] = mapped_column(JSONB, default=list)  # list of fear descriptions
    soft_spot: Mapped[str | None] = mapped_column(Text)  # What motivates to act
    trust_level: Mapped[int] = mapped_column(Integer, default=3)  # 1-10
    resistance_level: Mapped[int] = mapped_column(Integer, default=5)  # 1-10
    # Context
    lead_source: Mapped[str] = mapped_column(String(50), default="cold_base")
    call_history: Mapped[list] = mapped_column(JSONB, default=list)
    crm_notes: Mapped[str | None] = mapped_column(Text)
    # Hidden (manager doesn't see)
    hidden_objections: Mapped[list] = mapped_column(JSONB, default=list)
    trap_ids: Mapped[list] = mapped_column(JSONB, default=list)  # list of trap UUIDs
    chain_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("objection_chains.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cascade_ids: Mapped[list] = mapped_column(JSONB, default=list)  # list of TrapCascade UUIDs
    breaking_point: Mapped[str | None] = mapped_column(Text)
    # Scoring additions
    trap_results: Mapped[dict | None] = mapped_column(JSONB)  # Results of trap handling
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship(
        "TrainingSession", backref=backref("client_profile", uselist=False), foreign_keys=[session_id]
    )
    profession: Mapped["ProfessionProfile | None"] = relationship(back_populates="client_profiles")
    chain: Mapped["ObjectionChain | None"] = relationship(back_populates="client_profiles")


# ---------------------------------------------------------------------------
# v5 Models — Multi-call stories, personality profiles, episodic memory
# ---------------------------------------------------------------------------

class StageDirectionType(str, enum.Enum):
    """Stage direction tag types — v1 (existing) + v2 (new)."""
    # v1 existing
    emotion_trigger = "emotion_trigger"
    trap = "trap"
    action = "action"
    # v2 new
    memory = "memory"          # [MEMORY:...] — episodic memory write
    storylet = "storylet"      # [STORYLET:...] — micro-narrative trigger
    consequence = "consequence" # [CONSEQUENCE:...] — cross-call consequence
    factor = "factor"          # [FACTOR:...] — human factor activation


class PersonalityProfile(Base):
    """OCEAN Big-5 + PAD emotional dimensions — injected on top of archetype.

    OCEAN ranges are pre-correlated with archetype_code:
      aggressive → O:0.3-0.5  C:0.2-0.4  E:0.6-0.8  A:0.1-0.3  N:0.7-0.9
      anxious    → O:0.3-0.5  C:0.5-0.7  E:0.2-0.4  A:0.6-0.8  N:0.8-1.0
      skeptic    → O:0.4-0.6  C:0.6-0.8  E:0.4-0.6  A:0.2-0.4  N:0.4-0.6
      etc. (full correlation table in TZ-01 §4.2)

    PAD (Pleasure-Arousal-Dominance) is computed dynamically from emotion state
    but stored here as baseline values.
    """
    __tablename__ = "personality_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archetype_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # OCEAN Big-5 (0.0 — 1.0)
    openness: Mapped[float] = mapped_column(Float, nullable=False)
    conscientiousness: Mapped[float] = mapped_column(Float, nullable=False)
    extraversion: Mapped[float] = mapped_column(Float, nullable=False)
    agreeableness: Mapped[float] = mapped_column(Float, nullable=False)
    neuroticism: Mapped[float] = mapped_column(Float, nullable=False)

    # PAD baseline (−1.0 — +1.0)
    pleasure_baseline: Mapped[float] = mapped_column(Float, default=0.0)
    arousal_baseline: Mapped[float] = mapped_column(Float, default=0.0)
    dominance_baseline: Mapped[float] = mapped_column(Float, default=0.0)

    # OCC appraisal tendencies (JSONB for flexibility)
    # {"desirability_bias": -0.3, "praiseworthiness_bias": -0.2, "likelihood_bias": 0.4}
    occ_tendencies: Mapped[dict | None] = mapped_column(JSONB)

    # Behavioral modifiers derived from OCEAN
    # {"verbosity": 0.7, "formality": 0.3, "emotionality": 0.8, "assertiveness": 0.9}
    behavioral_modifiers: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClientStory(Base):
    """Multi-call story arc for a single client across multiple training sessions.

    Groups TrainingSessions into a coherent narrative where the client
    remembers previous calls, evolves attitudes, and reacts to consequences.

    personality_profile JSONB stores the full OCEAN/PAD snapshot for this story,
    correlated with archetype but randomized within ranges per TZ-01.
    """
    __tablename__ = "client_stories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    client_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Story arc metadata
    story_name: Mapped[str] = mapped_column(String(300), default="Untitled Story")
    total_calls_planned: Mapped[int] = mapped_column(Integer, default=3)
    current_call_number: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Personality snapshot for this story (OCEAN + PAD + modifiers)
    # Generated once at story creation, stays stable across calls
    personality_profile: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Format: {
    #   "ocean": {"O": 0.45, "C": 0.62, "E": 0.38, "A": 0.71, "N": 0.55},
    #   "pad_baseline": {"P": -0.2, "A": 0.3, "D": -0.1},
    #   "occ": {"desirability_bias": -0.3, ...},
    #   "modifiers": {"verbosity": 0.7, "formality": 0.3, ...}
    # }

    # Active human factors (accumulated across calls)
    active_factors: Mapped[list] = mapped_column(JSONB, default=list)
    # Format: [{"factor": "fatigue", "intensity": 0.7, "since_call": 2}, ...]

    # Between-call CRM simulation events
    between_call_events: Mapped[list] = mapped_column(JSONB, default=list)
    # Format: [
    #   {"after_call": 1, "event": "client_googled_bankruptcy", "impact": "increased_knowledge"},
    #   {"after_call": 2, "event": "creditor_called", "impact": "increased_anxiety"},
    # ]

    # Story-level consequences accumulated across calls
    consequences: Mapped[list] = mapped_column(JSONB, default=list)
    # Format: [{"call": 1, "type": "trust_broken", "severity": 0.8, "detail": "..."}, ...]

    # Compressed summary of older calls (managed by ContextBudgetManager)
    compressed_history: Mapped[str | None] = mapped_column(Text)

    # Game Director state
    director_state: Mapped[dict | None] = mapped_column(JSONB)
    # Format: {"tension_curve": [0.3, 0.6, 0.8], "pacing": "accelerating", "next_twist": "..."}

    # ── Game Director: narrative lifecycle fields (used by advance_story) ──
    # Relationship score: 0-100 trust meter, modified by empathy/rudeness/promises
    relationship_score: Mapped[float] = mapped_column(Float, default=50.0)
    # Lifecycle state machine: NEW_LEAD → FIRST_CONTACT → ... → DEAL_CLOSED/REJECTED
    lifecycle_state: Mapped[str] = mapped_column(String(50), default="FIRST_CONTACT")
    # Active storylets: list of storylet codes currently in play
    active_storylets: Mapped[dict] = mapped_column(JSONB, default=list)
    # Format: ["wife_found_out", "collectors_arrived"]
    # Consequence log: accumulated consequences across all calls
    consequence_log: Mapped[dict] = mapped_column(JSONB, default=list)
    # Format: [{"id": "...", "level": "local", "trigger_action": "...",
    #           "effect_description": "...", "is_active": true, ...}]
    # Memory: promises, key moments, and other structured memories from calls
    memory: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Format: {"promises": [...], "key_moments": [...]}
    # Total completed calls counter (incremented by game_director.advance_story)
    total_calls: Mapped[int] = mapped_column(Integer, default=0)

    # --- Voice assignment (persistent across calls, ТЗ-04 v2) ---
    voice_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="ElevenLabs voice_id, assigned on first call, permanent for this client"
    )
    voice_params_snapshot: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment='Frozen base params at assignment: {"stability":0.6,"similarity_boost":0.8,"style":0.2,"speed":1.0}'
    )
    # Couple mode voice config (when archetype = couple)
    couple_voice_config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment='{"partner_a": {"voice_id":"...","factors":[...],"pad":{...}}, "partner_b": {...}}'
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EpisodicMemory(Base):
    """Per-call episodic memory entries — what the client remembers from each call.

    Written by [MEMORY:...] stage directions during conversation.
    Read by build_multi_call_prompt() to inject into subsequent calls.
    Managed by ContextBudgetManager for token budget compliance.
    """
    __tablename__ = "episodic_memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Memory content
    memory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Types: "promise", "impression", "fact", "emotion", "objection", "rapport"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. "Менеджер обещал перезвонить с документами через 2 дня"

    # Salience for compression decisions (1-10, higher = keep longer)
    salience: Mapped[int] = mapped_column(Integer, default=5)

    # Emotional valence (−1.0 negative … +1.0 positive)
    valence: Mapped[float] = mapped_column(Float, default=0.0)

    # Whether this memory has been compressed into story summary
    is_compressed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Token count for budget management
    token_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StoryStageDirection(Base):
    """Parsed stage directions from LLM output during a story session.

    Captures both v1 tags ([emotion_trigger:X], [trap:Y]) and
    v2 tags ([MEMORY:...], [STORYLET:...], [CONSEQUENCE:...], [FACTOR:...]).
    Used for analytics and replay.
    """
    __tablename__ = "story_stage_directions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    story_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("client_stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    call_number: Mapped[int] = mapped_column(Integer, nullable=False)
    message_sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    direction_type: Mapped[StageDirectionType] = mapped_column(
        Enum(StageDirectionType), nullable=False
    )
    raw_tag: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. "[MEMORY:Менеджер обещал скидку 10%]"
    parsed_payload: Mapped[dict | None] = mapped_column(JSONB)
    # e.g. {"content": "Менеджер обещал скидку 10%", "salience": 7, "type": "promise"}

    was_applied: Mapped[bool] = mapped_column(Boolean, default=True)
    # False if parsing failed or direction was filtered

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
