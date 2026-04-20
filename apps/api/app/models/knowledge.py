"""Knowledge quiz models for 127-ФЗ knowledge testing.

Two modes:
1. AI Examiner — user tests knowledge against AI (RAG-based)
2. PvP Arena — 2 or 4 players compete, AI judges answers
"""

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QuizMode(str, enum.Enum):
    """Quiz session modes (DOC_11: 5→12)."""
    free_dialog = "free_dialog"         # Free-form Q&A with AI
    blitz = "blitz"                     # 20 questions, 60s each
    themed = "themed"                   # 10-15 questions on one category
    pvp = "pvp"                         # PvP duel (2 or 4 players)
    srs_review = "srs_review"           # Spaced repetition review
    # DOC_11: 7 new modes
    rapid_blitz = "rapid_blitz"         # 10Q, 30s, binary scoring (Level 7)
    case_study = "case_study"           # Court case + follow-up Qs (Level 6)
    debate = "debate"                   # 5-7 round dialogue (Level 8)
    mock_court = "mock_court"           # Courtroom simulation (Level 11)
    article_deep_dive = "article_deep_dive"  # 8-12 Qs per article (Level 5)
    team_quiz = "team_quiz"             # 4 players 2v2 (Level 10)
    daily_challenge = "daily_challenge"  # 10 daily Qs, global leaderboard (Level 4)


class QuizSessionStatus(str, enum.Enum):
    """Quiz session lifecycle states."""
    waiting = "waiting"            # PvP: waiting for opponents
    active = "active"              # In progress
    completed = "completed"        # Finished normally
    abandoned = "abandoned"        # User left
    expired = "expired"            # PvP: no one accepted challenge


class KnowledgeQuizSession(Base):
    """Quiz session (solo or PvP arena).

    HISTORY PRESERVATION CONTRACT (Phase C, 2026-04-20, owner-locked):
    Quiz history persists regardless of subscription — Scout users who
    re-subscribe months later must see their old scores/answers. Do NOT
    add retention cleanup or plan-gated read filters. See ``TrainingSession``
    for the same contract.
    """
    """A single knowledge testing session."""
    __tablename__ = "knowledge_quiz_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session owner (who started it)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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
    contains_bot: Mapped[bool] = mapped_column(Boolean, default=False)  # True if bot was in match
    anti_cheat_flags: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [{user_id, action}]
    rating_changes_applied: Mapped[bool] = mapped_column(Boolean, default=False)

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
        UUID(as_uuid=True), ForeignKey("knowledge_quiz_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Participant score
    score: Mapped[float] = mapped_column(Float, default=0.0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_answers: Mapped[int] = mapped_column(Integer, default=0)

    # Position after game ends (1st, 2nd, etc.)
    final_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Phase A (2026-04-20): progression bookkeeping for Duolingo-style UX.
    # streak_counter counts consecutive correct answers (resets on wrong);
    # xp_earned is the XP accrued across this session for post-match HUD.
    streak_counter: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    xp_earned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["KnowledgeQuizSession"] = relationship(back_populates="participants")


class KnowledgeAnswer(Base):
    """Individual answer in a quiz session."""
    __tablename__ = "knowledge_answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_quiz_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Who answered (for PvP mode)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
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
    rag_chunks_used: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # list of chunk IDs

    # Metadata
    hint_used: Mapped[bool] = mapped_column(Boolean, default=False)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["KnowledgeQuizSession"] = relationship(back_populates="answers")


class UserAnswerHistory(Base):
    """SM-2 spaced repetition tracking per user per question topic.

    Groups answers by (user_id, question_category, question_hash) to track
    how well a user recalls specific legal concepts over time.
    """
    __tablename__ = "user_answer_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Question identity (category + content hash for dedup)
    question_category: Mapped[str] = mapped_column(String(50), nullable=False)
    question_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 of question text
    question_text: Mapped[str] = mapped_column(Text, nullable=False)  # stored for reference

    # SM-2 parameters
    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)  # EF >= 1.3
    interval_days: Mapped[int] = mapped_column(Integer, default=1)  # days until next review
    repetition_count: Mapped[int] = mapped_column(Integer, default=0)  # consecutive correct
    quality_history: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # last N quality scores

    # Scheduling
    next_review_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Stats
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    total_correct: Mapped[int] = mapped_column(Integer, default=0)

    # Leitner box (hybrid extension: 0-4, higher = better retention)
    leitner_box: Mapped[int] = mapped_column(Integer, default=0)

    # Source tracking (where the question came from)
    source_type: Mapped[str] = mapped_column(String(20), default="quiz")  # quiz, pvp, training, blitz

    # Streak tracking
    current_streak: Mapped[int] = mapped_column(Integer, default=0)  # consecutive correct streak
    best_streak: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
        UUID(as_uuid=True), ForeignKey("knowledge_quiz_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Accepted by
    accepted_by: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # list of user_ids

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ──────────────────────────────────────────────────────────────────────
#  DOC_11: Knowledge v2 tables (migration 014)
# ──────────────────────────────────────────────────────────────────────


class DebateSession(Base):
    """Debate/mock-court session linked to a quiz session (DOC_11)."""

    __tablename__ = "debate_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    position: Mapped[str] = mapped_column("player_position", String(20), nullable=False, server_default="pro")
    ai_position: Mapped[str] = mapped_column(String(20), nullable=False, server_default="contra")
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    rounds_data: Mapped[dict | None] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamQuizTeam(Base):
    """Team entry for team_quiz mode (DOC_11)."""

    __tablename__ = "team_quiz_teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_name: Mapped[str] = mapped_column(String(1), nullable=False)  # "A" or "B"
    captain_id: Mapped[uuid.UUID] = mapped_column("player1_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    member_ids: Mapped[uuid.UUID | None] = mapped_column("player2_id", UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    score: Mapped[float] = mapped_column("team_score", Float, nullable=False, server_default="0.0")
    passes_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyChallenge(Base):
    """Daily knowledge challenge (DOC_11)."""

    __tablename__ = "daily_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenge_date: Mapped[datetime] = mapped_column(sa.Date(), nullable=False, unique=True)
    questions: Mapped[dict] = mapped_column(JSONB, nullable=False)
    category: Mapped[str | None] = mapped_column("personality", String(50), nullable=True)
    total_participants: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyChallengeEntry(Base):
    """User entry for a daily challenge (DOC_11)."""

    __tablename__ = "daily_challenge_entries"
    __table_args__ = (sa.UniqueConstraint("challenge_id", "user_id", name="uq_daily_entry_user"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_challenges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_quiz_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
