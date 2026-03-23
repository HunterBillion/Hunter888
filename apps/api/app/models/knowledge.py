"""Knowledge quiz models for 127-ФЗ knowledge testing.

Two modes:
1. AI Examiner — user tests knowledge against AI (RAG-based)
2. PvP Arena — 2 or 4 players compete, AI judges answers
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QuizMode(str, enum.Enum):
    """Quiz session modes."""
    free_dialog = "free_dialog"    # Free-form Q&A with AI
    blitz = "blitz"                # 20 questions, 60s each
    themed = "themed"              # 10-15 questions on one category
    pvp = "pvp"                    # PvP duel (2 or 4 players)


class QuizSessionStatus(str, enum.Enum):
    """Quiz session lifecycle states."""
    waiting = "waiting"            # PvP: waiting for opponents
    active = "active"              # In progress
    completed = "completed"        # Finished normally
    abandoned = "abandoned"        # User left
    expired = "expired"            # PvP: no one accepted challenge


class KnowledgeQuizSession(Base):
    """A single knowledge testing session."""
    __tablename__ = "knowledge_quiz_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session owner (who started it)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    mode: Mapped[QuizMode] = mapped_column(Enum(QuizMode), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # LegalCategory value
    difficulty: Mapped[int] = mapped_column(Integer, default=3)  # 1-5

    # Scoring
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_answers: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100%

    # PvP fields
    max_players: Mapped[int] = mapped_column(Integer, default=1)  # 1=solo, 2 or 4=pvp

    # Lifecycle
    status: Mapped[QuizSessionStatus] = mapped_column(
        Enum(QuizSessionStatus), default=QuizSessionStatus.active
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # AI personality used (for AI examiner mode)
    ai_personality: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    answers: Mapped[list["KnowledgeAnswer"]] = relationship(back_populates="session", lazy="selectin")
    participants: Mapped[list["QuizParticipant"]] = relationship(back_populates="session", lazy="selectin")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuizParticipant(Base):
    """Participant in a quiz session (for PvP mode, 2-4 players)."""
    __tablename__ = "quiz_participants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_quiz_sessions.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Participant score
    score: Mapped[float] = mapped_column(Float, default=0.0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_answers: Mapped[int] = mapped_column(Integer, default=0)

    # Position after game ends (1st, 2nd, etc.)
    final_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["KnowledgeQuizSession"] = relationship(back_populates="participants")


class KnowledgeAnswer(Base):
    """Individual answer in a quiz session."""
    __tablename__ = "knowledge_answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_quiz_sessions.id"), nullable=False, index=True
    )

    # Who answered (for PvP mode)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    # Question and answer
    question_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_category: Mapped[str] = mapped_column(String(50), nullable=False)
    user_answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Evaluation
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    article_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    score_delta: Mapped[float] = mapped_column(Float, default=0.0)

    # RAG context used
    rag_chunks_used: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # list of chunk IDs

    # Metadata
    hint_used: Mapped[bool] = mapped_column(Boolean, default=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["KnowledgeQuizSession"] = relationship(back_populates="answers")


class QuizChallenge(Base):
    """PvP challenge notification (Arena mode).

    When a user clicks 'Find opponent', a challenge is created.
    Other users receive notifications and can accept within 60 seconds.
    """
    __tablename__ = "quiz_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Challenge settings
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    max_players: Mapped[int] = mapped_column(Integer, default=2)  # 2 or 4

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_quiz_sessions.id"), nullable=True
    )

    # Accepted by
    accepted_by: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # list of user_ids

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
