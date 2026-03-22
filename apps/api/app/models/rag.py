"""Legal RAG models for 127-ФЗ knowledge base.

MVP: hardcoded legal checks (Phase 4 will add pgvector embeddings).
Stores validation results per session for audit and scoring (Layer 10).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

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

    MVP: populated via seed script with ~30 common legal facts.
    Phase 4: will add embedding column (pgvector) for semantic search.
    """
    __tablename__ = "legal_knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[LegalCategory] = mapped_column(Enum(LegalCategory), nullable=False, index=True)

    # The legal fact / rule
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. "Минимальный размер долга для подачи на банкротство — 500 000 рублей"

    # Law reference
    law_article: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. "127-ФЗ ст. 213.3 п.2"

    # Common incorrect statements that contradict this fact
    common_errors: Mapped[dict] = mapped_column(JSONB, default=list)
    # ["Банкротство можно подать при любой сумме долга", "Порог — 300 000 рублей"]

    # Keywords for MVP pattern matching (before pgvector)
    match_keywords: Mapped[dict] = mapped_column(JSONB, default=list)
    # ["минимальный долг", "порог банкротства", "500 000", "сумма долга"]

    # Correct response template for scoring reference
    correct_response_hint: Mapped[str | None] = mapped_column(Text)

    # Difficulty: how often managers get this wrong (1-10)
    error_frequency: Mapped[int] = mapped_column(Integer, default=5)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LegalValidationResult(Base):
    """Result of validating a manager's legal statement during a session.

    One row per detected legal claim in the conversation.
    Used by Layer 10 scoring to compute the ±5 modifier.
    """
    __tablename__ = "legal_validation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id"), nullable=False, index=True
    )
    message_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    # Which message in the conversation contained the legal claim

    # The manager's statement being validated
    manager_statement: Mapped[str] = mapped_column(Text, nullable=False)

    # Matched knowledge chunk (if any)
    knowledge_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_knowledge_chunks.id"), nullable=True
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
