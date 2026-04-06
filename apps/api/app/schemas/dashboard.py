"""Pydantic schemas for ROP Dashboard v2, Weekly Reports, and Benchmark."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Team Heatmap
# ---------------------------------------------------------------------------

class HeatmapCell(BaseModel):
    """Single skill score for one manager."""
    skill: str
    score: float = 0.0        # 0-100
    trend: str = "stable"     # improving | declining | stable


class HeatmapRow(BaseModel):
    """One manager's row in the heatmap."""
    user_id: uuid.UUID
    full_name: str
    avatar_url: str | None = None
    skills: list[HeatmapCell]
    avg_score: float = 0.0
    sessions_this_week: int = 0


class TeamHeatmapResponse(BaseModel):
    team_name: str
    skill_names: list[str]     # column headers
    rows: list[HeatmapRow]
    team_avg: dict[str, float] = Field(default_factory=dict)  # skill → avg


# ---------------------------------------------------------------------------
# Weak Links (managers needing attention)
# ---------------------------------------------------------------------------

class WeakLinkEntry(BaseModel):
    user_id: uuid.UUID
    full_name: str
    avatar_url: str | None = None
    reasons: list[str]         # ["declining 3+ days", "avg_score < 50", ...]
    avg_score: float = 0.0
    trend: str = "stable"
    sessions_this_week: int = 0
    last_session_at: datetime | None = None


class WeakLinksResponse(BaseModel):
    needs_attention: list[WeakLinkEntry]
    total_team: int = 0
    attention_count: int = 0


# ---------------------------------------------------------------------------
# Manager Benchmark (comparison within team)
# ---------------------------------------------------------------------------

class BenchmarkSkill(BaseModel):
    skill: str
    score: float = 0.0
    team_avg: float = 0.0
    diff: float = 0.0          # score - team_avg
    percentile: int = 50       # within team


class BenchmarkEntry(BaseModel):
    user_id: uuid.UUID
    full_name: str
    avatar_url: str | None = None
    overall_score: float = 0.0
    overall_rank: int = 0
    skills: list[BenchmarkSkill]
    sessions_count: int = 0


class BenchmarkResponse(BaseModel):
    team_name: str
    entries: list[BenchmarkEntry]
    team_avg_score: float = 0.0


# ---------------------------------------------------------------------------
# ROI Training
# ---------------------------------------------------------------------------

class ROIDataPoint(BaseModel):
    period: str                # "2026-W12"
    training_hours: float = 0.0
    sessions_count: int = 0
    avg_score_delta: float = 0.0
    skill_improvement: dict[str, float] = Field(default_factory=dict)


class ROIResponse(BaseModel):
    data_points: list[ROIDataPoint]
    correlation: float = 0.0   # Pearson correlation training_hours ↔ score_delta
    summary: str = ""


# ---------------------------------------------------------------------------
# Weekly Report
# ---------------------------------------------------------------------------

class WeeklyReportResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    week_start: datetime
    week_end: datetime
    sessions_completed: int = 0
    total_time_minutes: int = 0
    average_score: float | None = None
    best_score: int | None = None
    worst_score: int | None = None
    score_trend: str | None = None
    skills_snapshot: dict = Field(default_factory=dict)
    skills_change: dict = Field(default_factory=dict)
    weak_points: list = Field(default_factory=list)
    recommendations: list = Field(default_factory=list)
    report_text: str | None = None
    weekly_rank: int | None = None
    rank_change: int | None = None
    new_achievements: list = Field(default_factory=list)
    xp_earned: int = 0


class WeeklyReportHistoryResponse(BaseModel):
    reports: list[WeeklyReportResponse]
    total: int = 0


class TeamDigestEntry(BaseModel):
    user_id: uuid.UUID
    full_name: str
    sessions_completed: int = 0
    avg_score: float = 0.0
    score_trend: str = "stable"
    skills_change_summary: str = ""


class TeamDigestResponse(BaseModel):
    team_name: str
    week_start: datetime
    week_end: datetime
    total_sessions: int = 0
    avg_team_score: float = 0.0
    top_improvements: list[str] = Field(default_factory=list)
    degrading_members: list[str] = Field(default_factory=list)
    members: list[TeamDigestEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Platform Benchmark
# ---------------------------------------------------------------------------

class PlatformBenchmarkSkill(BaseModel):
    skill: str
    team_avg: float = 0.0
    platform_avg: float = 0.0
    percentile: int = 50


class PlatformBenchmarkResponse(BaseModel):
    team_name: str
    skills: list[PlatformBenchmarkSkill]
    team_sessions_per_week: float = 0.0
    platform_sessions_per_week: float = 0.0
    team_avg_score: float = 0.0
    platform_avg_score: float = 0.0
