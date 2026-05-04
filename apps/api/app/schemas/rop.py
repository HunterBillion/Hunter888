"""Pydantic schemas for Methodologist tools API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.rag import LegalCategory


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
# Arena Content CRUD — canonical shape matching apps/api/app/models/rag.py
# (LegalKnowledgeChunk). The earlier `ChunkCreateRequest` / `ChunkUpdateRequest`
# / `ChunkResponse` classes that lived here used `title` / `content` /
# `article_reference` — fields that DO NOT EXIST on the ORM. They were never
# imported by the handlers (which took `data: dict`) but their existence was
# misleading and TZ-3 §12.2 / §14.5 mandate their removal.
#
# UI-friendly aliases (`title` → `law_article`, `content` → `fact_text`) are
# accepted by the request-side adapter `to_orm_kwargs` below — the response
# always uses canonical names so the FE stays in sync with the model.
# ---------------------------------------------------------------------------


class ArenaChunkCreateRequest(BaseModel):
    """Canonical create payload for legal_knowledge_chunks.

    Accepts the FE legacy aliases `title` and `content` for backward
    compatibility with the ScenariosEditor → ArenaContentEditor MVP UI;
    they are folded into `law_article` / `fact_text` by `to_orm_kwargs`.
    Once the FE migrates to canonical names (planned for C5.1), remove
    the alias fields.

    Audit-2026-05-04 hardening:
      * `extra="forbid"` so `is_active` / `knowledge_status` / unknown
        fields raise 422 instead of silently dropping under a 200 OK.
        Pre-fix: `PUT {"is_active": false}` → 200 "Updated", but the
        flag never reached the ORM — operator believed the chunk was
        retired, RAG kept serving it.
      * `category: LegalCategory` so an unknown value raises 422 with
        a readable enum-list, not a 500 from the DB-layer enum cast.
      * Both create and update enforce `min_length=10` / `max_length=20000`
        on every text alias — the bare `content`/`title` fallbacks used to
        slip past the create validator and (worse) the update validator
        had no min_length at all, allowing `PUT {"fact_text":""}` to
        empty out a real chunk.
    """

    model_config = ConfigDict(extra="forbid")

    fact_text: str | None = Field(None, min_length=10, max_length=20000)
    law_article: str | None = Field(None, max_length=100)
    category: LegalCategory
    common_errors: list[str] = Field(default_factory=list)
    match_keywords: list[str] = Field(default_factory=list)
    correct_response_hint: str | None = None
    difficulty_level: int = Field(3, ge=1, le=5)
    is_court_practice: bool = False
    court_case_reference: str | None = None
    question_templates: list[dict] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # ── Legacy aliases (deprecated, accepted during transition) ──
    title: str | None = Field(None, max_length=300)
    content: str | None = Field(None, min_length=10, max_length=20000)
    article_reference: str | None = Field(None, max_length=100)

    def to_orm_kwargs(self) -> dict:
        """Translate to the canonical ORM kwargs.

        Resolution rules:
          * `fact_text` wins over `content`.
          * `law_article` wins over `article_reference`, which wins
            over `title` (title is a generic UI label; only used as
            article_reference fallback to keep legacy seeds importable).
          * UNKNOWN keys are NOT silently passed through — every key in
            the returned dict is a real LegalKnowledgeChunk column name
            (verified by the AST guard in tests/test_arena_chunk_
            invariants.py).
        """
        fact = self.fact_text or self.content
        article = self.law_article or self.article_reference or self.title
        if not fact:
            raise ValueError("fact_text (or alias `content`) is required")
        if not article:
            raise ValueError(
                "law_article (or alias `article_reference` / `title`) is required"
            )
        return {
            "fact_text": fact,
            "law_article": article,
            "category": self.category,
            "common_errors": list(self.common_errors),
            "match_keywords": list(self.match_keywords),
            "correct_response_hint": self.correct_response_hint,
            "difficulty_level": self.difficulty_level,
            "is_court_practice": self.is_court_practice,
            "court_case_reference": self.court_case_reference,
            "question_templates": list(self.question_templates),
            "tags": list(self.tags),
        }


class ArenaChunkUpdateRequest(BaseModel):
    """Partial update — only fields explicitly set are written. Same
    alias rules as create.

    Audit-2026-05-04: empty-string `fact_text`/`content` would have
    silently wiped the chunk's text under a 200 "Updated" response (and
    the SQLAlchemy `before_update` listener then null'd the embedding,
    making the wreckage invisible to RAG). Both fields are now bounded
    `min_length=10`. Same `extra="forbid"` policy as create — fields
    like `is_active` / `knowledge_status` aren't in the schema; passing
    them used to return 200 OK with no effect on the chunk."""

    model_config = ConfigDict(extra="forbid")

    fact_text: str | None = Field(None, min_length=10, max_length=20000)
    law_article: str | None = Field(None, max_length=100)
    category: LegalCategory | None = None
    common_errors: list[str] | None = None
    match_keywords: list[str] | None = None
    correct_response_hint: str | None = None
    difficulty_level: int | None = Field(None, ge=1, le=5)
    is_court_practice: bool | None = None
    court_case_reference: str | None = None
    question_templates: list[dict] | None = None
    tags: list[str] | None = None
    # ── Legacy aliases ──
    title: str | None = Field(None, max_length=300)
    content: str | None = Field(None, min_length=10, max_length=20000)
    article_reference: str | None = Field(None, max_length=100)

    def to_orm_kwargs(self) -> dict:
        """Same alias resolution as the create request, but only sets
        the keys that were explicitly supplied."""
        out: dict = {}
        fact = self.fact_text if self.fact_text is not None else self.content
        if fact is not None:
            out["fact_text"] = fact
        article = (
            self.law_article
            if self.law_article is not None
            else (self.article_reference or self.title)
        )
        if article is not None:
            out["law_article"] = article
        for canonical in (
            "category",
            "common_errors",
            "match_keywords",
            "correct_response_hint",
            "difficulty_level",
            "is_court_practice",
            "court_case_reference",
            "question_templates",
            "tags",
        ):
            value = getattr(self, canonical)
            if value is not None:
                out[canonical] = value
        return out


class ArenaChunkResponse(BaseModel):
    """Response uses canonical names ONLY. FE adapts via local mapping
    if a UI label like "Заголовок" is desired.

    Audit-2026-05-04: previously the API hand-truncated `fact_text` to
    `[:200] + "..."` for every list-row, so the UI literally never saw
    the tail of any chunk (375/375 affected on prod). Truncation is
    gone — FE renders full text, with optional clamp via CSS.
    """

    id: uuid.UUID
    fact_text: str
    law_article: str
    category: str
    common_errors: list[str] = Field(default_factory=list)
    match_keywords: list[str] = Field(default_factory=list)
    correct_response_hint: str | None = None
    difficulty_level: int = 3
    is_court_practice: bool = False
    court_case_reference: str | None = None
    question_templates: list[dict] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None
    # Diagnostics so the FE can flag "embedding pending" rows.
    embedding_ready: bool = False
    retrieval_count: int = 0


class ArenaChunkListResponse(BaseModel):
    items: list[ArenaChunkResponse]
    total: int
