"""Pydantic schemas for Methodologist tools API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Session Browser
# ---------------------------------------------------------------------------

class SessionFilterRequest(BaseModel):
    user_id: uuid.UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_score: float | None = None
    max_score: float | None = None
    archetype: str | None = None
    scenario: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class SessionBriefResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    scenario_title: str | None = None
    archetype: str | None = None
    score_total: float | None = None
    status: str
    duration_seconds: int | None = None
    started_at: datetime
    completed_at: datetime | None = None


class SessionListResponse(BaseModel):
    items: list[SessionBriefResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


# ---------------------------------------------------------------------------
# Scenario Management
# ---------------------------------------------------------------------------

class ScenarioCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = ""
    scenario_type: str = Field(..., description="cold_ad | warm_callback | in_website | etc.")
    archetype: str = Field(..., description="skeptic | anxious | passive | etc.")
    difficulty: int = Field(3, ge=1, le=10)
    client_brief: str = ""
    emotional_profile: dict = Field(default_factory=dict)
    traps: list[str] = Field(default_factory=list)
    success_criteria: dict = Field(default_factory=dict)


class ScenarioUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    difficulty: int | None = Field(None, ge=1, le=10)
    client_brief: str | None = None
    emotional_profile: dict | None = None
    traps: list[str] | None = None
    success_criteria: dict | None = None
    is_active: bool | None = None


class ScenarioResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    scenario_type: str
    archetype: str
    difficulty: int = 3
    client_brief: str | None = None
    is_active: bool = True
    created_at: datetime
    usage_count: int = 0


# ---------------------------------------------------------------------------
# Scoring Config
# ---------------------------------------------------------------------------

class ScoringConfigResponse(BaseModel):
    weights: dict[str, float]  # L1-L10 weights
    thresholds: dict[str, dict]  # Per-metric thresholds
    updated_at: datetime | None = None
    updated_by: str | None = None


class ScoringConfigUpdateRequest(BaseModel):
    weights: dict[str, float] | None = None
    thresholds: dict[str, dict] | None = None


# ---------------------------------------------------------------------------
# Arena Content CRUD
# ---------------------------------------------------------------------------

class ChunkCreateRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    content: str = Field(..., min_length=10)
    category: str
    article_reference: str | None = None
    difficulty_level: int = Field(3, ge=1, le=5)
    is_court_practice: bool = False
    court_case_reference: str | None = None
    question_templates: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ChunkUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    article_reference: str | None = None
    difficulty_level: int | None = Field(None, ge=1, le=5)
    is_court_practice: bool | None = None
    court_case_reference: str | None = None
    question_templates: list[str] | None = None
    tags: list[str] | None = None


class ChunkResponse(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    category: str
    article_reference: str | None = None
    difficulty_level: int = 3
    is_court_practice: bool = False
    court_case_reference: str | None = None
    question_templates: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


class ChunkListResponse(BaseModel):
    items: list[ChunkResponse]
    total: int
