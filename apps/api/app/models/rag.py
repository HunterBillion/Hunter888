"""RAG models for legal knowledge (127-ФЗ) and character personality (lorebook).

Legal: Stores validation results per session for audit and scoring (Layer 10).
Personality: Lorebook entries for character archetypes — keyword-triggered context injection.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.database import Base


class LegalAccuracy(str, enum.Enum):
    """Legal statement accuracy classification."""
    correct = "correct"          # Factually correct per 127-ФЗ
    correct_cited = "correct_cited"  # Correct AND cited specific article → +1 bonus
    partial = "partial"          # Partially correct, missing nuance → -1
    incorrect = "incorrect"      # Factually wrong → -3
    not_applicable = "n/a"       # Statement doesn't involve legal claims


class LegalCategory(str, enum.Enum):
    """Categories of legal knowledge in БФЛ context."""
    eligibility = "eligibility"          # Условия подачи на банкротство
    procedure = "procedure"              # Порядок процедуры
    property = "property"                # Имущество и его защита
    consequences = "consequences"        # Последствия банкротства
    costs = "costs"                      # Стоимость и расходы
    creditors = "creditors"              # Взаимодействие с кредиторами
    documents = "documents"              # Необходимые документы
    timeline = "timeline"                # Сроки процедуры
    court = "court"                      # Судебные процессы
    rights = "rights"                    # Права должника


class LegalKnowledgeChunk(Base):
    """A single unit of legal knowledge for 127-ФЗ.

    Each chunk represents one legal fact, procedure, or judicial precedent.
    Used by RAG pipeline for question generation, answer evaluation, and L10 scoring.
    Supports: pgvector semantic search, keyword fallback, blitz pre-built Q&A.
    """
    __tablename__ = "legal_knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[LegalCategory] = mapped_column(Enum(LegalCategory), nullable=False, index=True)

    # ── Core content ──────────────────────────────────────────────────────────
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    law_article: Mapped[str] = mapped_column(String(100), nullable=False)
    common_errors: Mapped[dict] = mapped_column(JSONB, default=list)
    match_keywords: Mapped[dict] = mapped_column(JSONB, default=list)
    correct_response_hint: Mapped[str | None] = mapped_column(Text)
    error_frequency: Mapped[int] = mapped_column(Integer, default=5)

    # ── Difficulty & question generation ──────────────────────────────────────
    difficulty_level: Mapped[int] = mapped_column(Integer, default=3, index=True)
    # 1=базовый (определение), 2=простой (цифра/срок), 3=средний (процедура),
    # 4=продвинутый (связь статей), 5=экспертный (судебная практика)

    question_templates: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # [{"text": "Каков порог?", "difficulty": 2, "expected_answer_keywords": ["500"]}]

    follow_up_questions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # ["А знаете ли вы разницу между правом и обязанностью подачи?"]

    related_chunk_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # ["uuid1", "uuid2"] — for cross-referencing and follow-up chains

    # ── Court practice ────────────────────────────────────────────────────────
    court_case_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # "Определение ВС РФ от 25.01.2018 №304-ЭС17-15555"

    is_court_practice: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # ── Blitz mode (zero-LLM questions) ───────────────────────────────────────
    blitz_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Short question: "Минимальный порог долга для обязательного банкротства ФЛ?"

    blitz_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Short answer: "500 000 рублей при просрочке от 3 месяцев"

    # ── 2026-04-20: Multiple-choice options for blitz mode ────────────────────
    # If present (2-4 strings), the warm-up UI renders radio options instead
    # of the free-form textarea. `correct_choice_index` is 0-based.
    # NULL = use free-form flow (legacy).
    choices: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    correct_choice_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Deep context ──────────────────────────────────────────────────────────
    source_article_full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full text of the relevant law article (for deep evaluation)

    # ── Versioning & metadata ─────────────────────────────────────────────────
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Tracks which embedding model was used (e.g. "gemini-embedding-001")

    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # ["каверзный", "судебная_практика", "пленум", "начинающий"]

    content_hash: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True)
    # md5(fact_text + law_article) — for idempotent seed upserts

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Embedding (pgvector) ──────────────────────────────────────────────────
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    # ── Feedback loop stats (auto-updated from user performance) ──────────────
    retrieval_count: Mapped[int] = mapped_column(Integer, default=0)
    # How many times this chunk was retrieved by RAG pipeline

    correct_answer_count: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_answer_count: Mapped[int] = mapped_column(Integer, default=0)
    # Aggregated from KnowledgeAnswer + LegalValidationResult

    effectiveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # correct / (correct + incorrect) — null until enough data (min 3 answers)

    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Last time this chunk was retrieved in any session

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class ChunkUsageLog(Base):
    """Log of every RAG chunk retrieval and its outcome.

    Tracks which chunks are actually used, in what context, and whether
    the user's answer was correct. Aggregated periodically to update
    LegalKnowledgeChunk.error_frequency / effectiveness_score.
    """
    __tablename__ = "chunk_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_knowledge_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Context of usage
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # "training" | "pvp_duel" | "quiz" | "blitz" | "validation"
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # FK to training_sessions.id / pvp_duels.id / knowledge_quiz_sessions.id

    # Retrieval context
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # "embedding" | "keyword" | "hybrid" | "blitz_pool"
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Position in results (1 = top result)

    # Outcome (filled after answer evaluation)
    was_answered: Mapped[bool] = mapped_column(Boolean, default=False)
    answer_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # null = not yet evaluated, True = user got it right, False = wrong
    user_answer_excerpt: Mapped[str | None] = mapped_column(String(500), nullable=True)
    score_delta: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Discovery: new errors not in common_errors
    discovered_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # If user made a new type of error not in chunk.common_errors

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LegalValidationResult(Base):
    """Result of validating a manager's legal statement during a session.

    One row per detected legal claim in the conversation.
    Used by Layer 10 scoring to compute the ±5 modifier.
    """
    __tablename__ = "legal_validation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=False, index=True
    )
    message_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    # Which message in the conversation contained the legal claim

    # The manager's statement being validated
    manager_statement: Mapped[str] = mapped_column(Text, nullable=False)

    # Matched knowledge chunk (if any)
    knowledge_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_knowledge_chunks.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Classification result
    accuracy: Mapped[LegalAccuracy] = mapped_column(Enum(LegalAccuracy), nullable=False)
    score_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # +1 for correct_cited, 0 for correct, -1 for partial, -3 for incorrect

    # Explanation for the manager (shown in post-session report)
    explanation: Mapped[str | None] = mapped_column(Text)
    # e.g. "Вы указали порог 300 000 руб., но по ст. 213.3 п.2 порог — 500 000 руб."

    # Reference to the correct law article
    law_reference: Mapped[str | None] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ═══════════════════════════════════════════════════════════════════════════════
# PERSONALITY RAG — Lorebook entries for character archetypes
# ═══════════════════════════════════════════════════════════════════════════════


class TraitCategory(str, enum.Enum):
    """Categories of personality lorebook entries."""
    core_identity = "core_identity"
    financial_situation = "financial_situation"
    backstory = "backstory"
    family_context = "family_context"
    legal_fears = "legal_fears"
    objection_price = "objection_price"
    objection_trust = "objection_trust"
    objection_necessity = "objection_necessity"
    objection_time = "objection_time"
    objection_competitor = "objection_competitor"
    breakpoint_trust = "breakpoint_trust"
    speech_examples = "speech_examples"
    emotional_triggers = "emotional_triggers"
    decision_drivers = "decision_drivers"


class PersonalityChunkSource(str, enum.Enum):
    """How this entry was created."""
    manual = "manual"
    extracted = "extracted"
    generated = "generated"
    learned = "learned"


class PersonalityChunk(Base):
    """A single lorebook entry for a character archetype.

    Each chunk = one piece of character knowledge injected into the prompt
    when triggered by keywords. Replaces monolithic 25K character prompt files.
    """
    __tablename__ = "personality_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archetype_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    trait_category: Mapped[TraitCategory] = mapped_column(Enum(TraitCategory), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[dict] = mapped_column(JSONB, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    source: Mapped[PersonalityChunkSource] = mapped_column(
        Enum(PersonalityChunkSource), default=PersonalityChunkSource.manual
    )

    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)

    retrieval_count: Mapped[int] = mapped_column(Integer, default=0)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    effectiveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    content_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    examples: Mapped[list["PersonalityExample"]] = relationship(
        back_populates="chunk", cascade="all, delete-orphan"
    )


class PersonalityExample(Base):
    """A few-shot dialogue example for RAG retrieval.

    Retrieved by semantic similarity to user message. Injected as 3-5 examples
    showing how the character speaks in similar situations.
    """
    __tablename__ = "personality_examples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("personality_chunks.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    archetype_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    situation: Mapped[str] = mapped_column(Text, nullable=False)
    dialogue: Mapped[str] = mapped_column(Text, nullable=False)
    emotion: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source: Mapped[PersonalityChunkSource] = mapped_column(
        Enum(PersonalityChunkSource), default=PersonalityChunkSource.extracted
    )

    embedding: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    retrieval_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    chunk: Mapped["PersonalityChunk | None"] = relationship(back_populates="examples")
