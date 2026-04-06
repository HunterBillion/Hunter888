"""Tournament model: weekly competitive scenarios with fixed conditions."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TournamentFormat(str, enum.Enum):
    """Tournament format: leaderboard (classic) or bracket (knockout)."""
    leaderboard = "leaderboard"
    bracket = "bracket"


class TournamentType(str, enum.Enum):
    """DOC_12: 4 tournament types."""
    weekly_sprint = "weekly_sprint"
    monthly_championship = "monthly_championship"
    themed = "themed"
    team = "team"


class BracketMatchFormat(str, enum.Enum):
    """Match format within bracket tournaments."""
    bo1 = "bo1"
    bo3 = "bo3"


class BracketMatchStatus(str, enum.Enum):
    """Status of a bracket match."""

    pending = "pending"      # Waiting for both players
    active = "active"        # Match in progress (duel created)
    completed = "completed"  # Winner determined
    bye = "bye"              # Auto-win (odd bracket)


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=False, index=True
    )
    # Fixed client profile seed — all participants get identical client
    client_seed: Mapped[dict | None] = mapped_column(JSONB)
    week_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    week_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)  # attempts per user
    bonus_xp_first: Mapped[int] = mapped_column(Integer, default=200)
    bonus_xp_second: Mapped[int] = mapped_column(Integer, default=100)
    bonus_xp_third: Mapped[int] = mapped_column(Integer, default=50)
    # Bracket/knockout support
    format: Mapped[str] = mapped_column(
        String(20), default=TournamentFormat.leaderboard.value, server_default="leaderboard"
    )
    bracket_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 8, 16, 32
    registration_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_round_num: Mapped[int] = mapped_column(Integer, default=0)  # 0=registration, 1=R1, etc.
    round_deadline_hours: Mapped[int] = mapped_column(Integer, default=24)  # hours before forfeit
    bracket_data: Mapped[dict | None] = mapped_column(JSONB)  # {seed_order: [...], ...}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # DOC_12: Tournament type + themed/team extensions
    tournament_type: Mapped[str] = mapped_column(String(30), default="weekly_sprint", server_default="weekly_sprint")
    theme_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    archetype_filter: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    difficulty_filter: Mapped[str | None] = mapped_column(String(20), nullable=True)


class TournamentEntry(Base):
    __tablename__ = "tournament_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TournamentParticipant(Base):
    """Registered participant for a bracket tournament."""

    __tablename__ = "tournament_participants"
    __table_args__ = (
        Index("ix_tp_tournament_user", "tournament_id", "user_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1=top seed
    rating_snapshot: Mapped[float] = mapped_column(Float, default=1500.0)
    eliminated_at_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_placement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BracketMatch(Base):
    """Single match in a bracket tournament."""

    __tablename__ = "bracket_matches"
    __table_args__ = (
        Index("ix_bm_tournament_round", "tournament_id", "round_num", "match_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round_num: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=first round
    match_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based within round
    player1_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    player2_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    winner_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    duel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pvp_duels.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default=BracketMatchStatus.pending.value
    )
    player1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    player2_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    forfeit_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    forfeit_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # DOC_12: BO3 support for semifinals/finals
    match_format: Mapped[str] = mapped_column(String(10), default="bo1", server_default="bo1")
    games: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # [{game_num, duel_id, winner_id, p1_score, p2_score}]
    games_won_p1: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    games_won_p2: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


# ---------------------------------------------------------------------------
# DOC_12: New Tournament Models
# ---------------------------------------------------------------------------

class TournamentTheme(Base):
    """Themed tournament definition (monthly rotation)."""
    __tablename__ = "tournament_themes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    archetype_filter: Mapped[list] = mapped_column(JSONB, nullable=False)
    difficulty_filter: Mapped[str | None] = mapped_column(String(20), nullable=True)
    scenario_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    icon_emoji: Mapped[str] = mapped_column(String(10), nullable=False, default="\U0001F3C6")
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TournamentTeam(Base):
    """Team registration for team tournaments."""
    __tablename__ = "tournament_teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    team_name: Mapped[str] = mapped_column(String(50), nullable=False)
    captain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    member_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    team_rating: Mapped[float] = mapped_column(Float, default=1500.0)
    motto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[float] = mapped_column(Float, default=0.0)
    eliminated: Mapped[bool] = mapped_column(Boolean, default=False)
    final_placement: Mapped[int | None] = mapped_column(Integer, nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeamMatch(Base):
    """Match between two teams in a team tournament."""
    __tablename__ = "team_matches"
    __table_args__ = (
        Index("ix_team_matches_round", "tournament_id", "round_num", "match_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True)
    round_num: Mapped[int] = mapped_column(Integer, nullable=False)
    match_index: Mapped[int] = mapped_column(Integer, nullable=False)
    team_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tournament_teams.id", ondelete="CASCADE"), nullable=False)
    team_b_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tournament_teams.id", ondelete="CASCADE"), nullable=True)
    team_a_score: Mapped[float] = mapped_column(Float, default=0.0)
    team_b_score: Mapped[float] = mapped_column(Float, default=0.0)
    winner_team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tournament_teams.id", ondelete="SET NULL"), nullable=True)
    individual_duels: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
