"""Pydantic schemas for Knowledge Quiz (127-FZ testing) REST API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

class CategoryProgress(BaseModel):
    """Single category with user progress stats."""
    category: str
    display_name: str
    total_questions_answered: int = 0
    correct_answers: int = 0
    accuracy_percent: float = 0.0
    sessions_count: int = 0
    best_score: float = 0.0
    last_attempt_at: datetime | None = None


class CategoriesResponse(BaseModel):
    categories: list[CategoryProgress]


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    """Create a new quiz session."""
    mode: str = Field(..., description="Quiz mode: free_dialog | blitz | themed | pvp")
    category: str | None = Field(None, description="Category slug (required for themed mode)")
    difficulty: int = Field(3, ge=1, le=5, description="Difficulty 1-5")
    max_players: int = Field(1, ge=1, le=4, description="1=solo, 2 or 4=pvp")
    ai_personality: str | None = Field(None, description="AI examiner personality")


class AnswerResponse(BaseModel):
    id: uuid.UUID
    question_number: int
    question_text: str
    question_category: str
    user_answer: str
    is_correct: bool
    explanation: str
    article_reference: str | None = None
    score_delta: float = 0.0
    hint_used: bool = False
    response_time_ms: int | None = None
    created_at: datetime


class ParticipantResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    score: float = 0.0
    correct_answers: int = 0
    incorrect_answers: int = 0
    final_rank: int | None = None
    joined_at: datetime


class SessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    mode: str
    category: str | None = None
    difficulty: int = 3
    total_questions: int = 0
    correct_answers: int = 0
    incorrect_answers: int = 0
    skipped: int = 0
    score: float = 0.0
    max_players: int = 1
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    ai_personality: str | None = None
    created_at: datetime


class SessionDetailResponse(SessionResponse):
    """Session with answers and participants."""
    answers: list[AnswerResponse] = Field(default_factory=list)
    participants: list[ParticipantResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class HistoryEntry(BaseModel):
    id: uuid.UUID
    mode: str
    category: str | None = None
    status: str
    score: float = 0.0
    total_questions: int = 0
    correct_answers: int = 0
    duration_seconds: int | None = None
    started_at: datetime
    ended_at: datetime | None = None


class HistoryResponse(BaseModel):
    items: list[HistoryEntry]
    total: int
    page: int
    page_size: int
    has_next: bool


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------

class CategoryProgressDetail(BaseModel):
    category: str
    display_name: str
    total_sessions: int = 0
    total_questions: int = 0
    correct_answers: int = 0
    accuracy_percent: float = 0.0
    avg_score: float = 0.0
    best_score: float = 0.0
    trend: str = "stable"  # improving | declining | stable


class OverallProgressResponse(BaseModel):
    total_sessions: int = 0
    total_questions: int = 0
    overall_accuracy: float = 0.0
    avg_score: float = 0.0
    categories: list[CategoryProgressDetail] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Weak Areas
# ---------------------------------------------------------------------------

class WeakArea(BaseModel):
    category: str
    display_name: str
    accuracy_percent: float = 0.0
    total_questions: int = 0
    incorrect_answers: int = 0
    recommendation: str = ""


class WeakAreasResponse(BaseModel):
    weak_areas: list[WeakArea]


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: uuid.UUID
    display_name: str
    total_score: float = 0.0
    sessions_count: int = 0
    avg_accuracy: float = 0.0


class KnowledgeLeaderboardResponse(BaseModel):
    entries: list[LeaderboardEntry]
    user_rank: int | None = None
    total_players: int = 0


# ---------------------------------------------------------------------------
# Challenges (PvP)
# ---------------------------------------------------------------------------

class ChallengeCreateRequest(BaseModel):
    category: str | None = Field(None, description="Category for challenge")
    max_players: int = Field(2, ge=2, le=4, description="2 or 4 players")


class ChallengeResponse(BaseModel):
    id: uuid.UUID
    challenger_id: uuid.UUID
    category: str | None = None
    max_players: int = 2
    is_active: bool = True
    session_id: uuid.UUID | None = None
    accepted_by: list[uuid.UUID] = Field(default_factory=list)
    expires_at: datetime
    created_at: datetime


class ActiveChallengesResponse(BaseModel):
    challenges: list[ChallengeResponse]


# ---------------------------------------------------------------------------
# Arena Leaderboard (3-period)
# ---------------------------------------------------------------------------

class ArenaLeaderboardEntryElo(BaseModel):
    """Leaderboard entry for all-time ELO-based ranking."""
    rank: int
    user_id: uuid.UUID
    username: str
    avatar_url: str | None = None
    rating: float = 1500.0
    rank_tier: str = "unranked"
    wins: int = 0
    losses: int = 0
    streak: int = 0
    best_streak: int = 0


class ArenaLeaderboardEntryScore(BaseModel):
    """Leaderboard entry for time-period score-based ranking."""
    rank: int
    user_id: uuid.UUID
    username: str
    avatar_url: str | None = None
    total_score: float = 0.0
    sessions_count: int = 0
    avg_score: float = 0.0


class ArenaLeaderboardResponse(BaseModel):
    period: str  # "week" | "month" | "all"
    entries: list[ArenaLeaderboardEntryElo | ArenaLeaderboardEntryScore]
    user_rank: dict | None = None
    total_players: int = 0


# ---------------------------------------------------------------------------
# DOC_11: New Knowledge Modes (7 new modes)
# ---------------------------------------------------------------------------

class DailyChallengeResponse(BaseModel):
    """Response for daily challenge endpoint."""
    challenge_id: uuid.UUID
    challenge_date: str
    questions_count: int
    category: str | None = None
    already_attempted: bool = False
    your_score: float | None = None
    your_rank: int | None = None
    total_participants: int = 0

    model_config = {"from_attributes": True}


class DailyChallengeLeaderboardEntry(BaseModel):
    rank: int
    user_id: uuid.UUID
    username: str
    score: float = 0.0


class DailyChallengeLeaderboardResponse(BaseModel):
    challenge_id: uuid.UUID
    challenge_date: str
    entries: list[DailyChallengeLeaderboardEntry]
    total_participants: int = 0


class DebateRoundData(BaseModel):
    """Single debate round data."""
    round_number: int
    player_argument: str
    ai_response: str
    score: float = 0.0
    feedback: str = ""


class DebateSessionResponse(BaseModel):
    """Debate/mock-court session response."""
    session_id: uuid.UUID
    topic: str
    position: str
    ai_position: str
    total_rounds: int
    current_round: int = 0
    rounds: list[DebateRoundData] = Field(default_factory=list)
    total_score: float = 0.0

    model_config = {"from_attributes": True}


# ── PR-6: User reports about AI verdicts (knowledge_answer_reports) ──

class AnswerReportRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AnswerReportResponse(BaseModel):
    id: str
    answer_id: str
    reporter_id: str
    reason: str
    status: str
    created_at: str
    linked_chunk_ids: list[str] | None = None

    model_config = {"from_attributes": True}
