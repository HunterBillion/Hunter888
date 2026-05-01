"""Pydantic schemas for the methodology REST API (TZ-8 PR-B).

Mirrors the validation contract spelled out in TZ-8 §4.4 — short
title, body capped at 10 000 chars, ≤ 20 entries in tags/keywords,
``kind`` constrained to the :class:`MethodologyKind` enum.

Three create/update flavours intentionally:

  * ``MethodologyChunkCreate`` — what the form sends. No id, no
    audit fields, no embedding fields.
  * ``MethodologyChunkUpdate`` — every field optional (PATCH-shape
    PUT). Endpoints choose to apply only set fields.
  * ``MethodologyChunkOut`` — what the API returns. Includes the
    governance state, the embedding-pending flag, and audit
    timestamps so the UI can render the status chip without a
    second round-trip.

Why not Pydantic ``Field(default_factory=...)`` on the create
schema? Because pydantic v2 + the current FastAPI + the
``model_config = {"from_attributes": True}`` shape of the rest of
the project plays badly with mutable defaults inside class body.
The endpoint coerces ``tags=None`` / ``keywords=None`` into ``[]``
on the way to the model, keeping the schema declarative.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Mirror of MethodologyKind enum values; we don't import the model
# enum directly here to keep the schema layer DB-free, but the
# ``test_methodology_*`` suite asserts the literal stays in sync
# with ``app.models.methodology.MethodologyKind``.
MethodologyKindLiteral = Literal[
    "opener",
    "objection",
    "closing",
    "discovery",
    "persona_tone",
    "counter_fact",
    "process",
    "other",
]

KnowledgeStatusLiteral = Literal["actual", "disputed", "outdated", "needs_review"]


# ── Validation limits (single source of truth) ──────────────────────────

TITLE_MAX = 200
BODY_MIN = 10
BODY_MAX = 10_000
LIST_FIELD_MAX = 20
LIST_ITEM_MAX = 60


def _validate_string_list(values: list[str] | None, field_name: str) -> list[str]:
    if values is None:
        return []
    if len(values) > LIST_FIELD_MAX:
        raise ValueError(
            f"{field_name} accepts at most {LIST_FIELD_MAX} items, got {len(values)}"
        )
    cleaned: list[str] = []
    for raw in values:
        s = (raw or "").strip()
        if not s:
            continue
        if len(s) > LIST_ITEM_MAX:
            raise ValueError(
                f"{field_name} item must be ≤ {LIST_ITEM_MAX} chars, "
                f"got {len(s)} (offending: {s[:30]!r}…)"
            )
        cleaned.append(s)
    return cleaned


# ── Request bodies ──────────────────────────────────────────────────────


class MethodologyChunkCreate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)
    body: str = Field(min_length=BODY_MIN, max_length=BODY_MAX)
    kind: MethodologyKindLiteral
    tags: list[str] | None = None
    keywords: list[str] | None = None

    @field_validator("title")
    @classmethod
    def _title_strip_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty after strip")
        return v

    @field_validator("body")
    @classmethod
    def _body_strip_nonempty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < BODY_MIN:
            raise ValueError(f"body must be ≥ {BODY_MIN} chars after strip")
        return v

    @field_validator("tags")
    @classmethod
    def _tags_validator(cls, v: list[str] | None) -> list[str]:
        return _validate_string_list(v, "tags")

    @field_validator("keywords")
    @classmethod
    def _keywords_validator(cls, v: list[str] | None) -> list[str]:
        return _validate_string_list(v, "keywords")


class MethodologyChunkUpdate(BaseModel):
    """PATCH-shape PUT. None means "don't touch"; explicit value
    overwrites; empty list / empty string overwrites with empty.
    """

    title: str | None = Field(default=None, max_length=TITLE_MAX)
    body: str | None = Field(default=None, max_length=BODY_MAX)
    kind: MethodologyKindLiteral | None = None
    tags: list[str] | None = None
    keywords: list[str] | None = None

    @field_validator("title")
    @classmethod
    def _title_validator(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("title cannot be set to empty")
        return v

    @field_validator("body")
    @classmethod
    def _body_validator(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) < BODY_MIN:
            raise ValueError(f"body must be ≥ {BODY_MIN} chars after strip")
        return v

    @field_validator("tags")
    @classmethod
    def _tags_validator(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _validate_string_list(v, "tags")

    @field_validator("keywords")
    @classmethod
    def _keywords_validator(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _validate_string_list(v, "keywords")


class MethodologyStatusUpdate(BaseModel):
    """Body for PATCH ``/methodology/chunks/{id}/status``.

    ``note`` is required when transitioning to ``disputed`` or
    ``outdated`` so future reviewers see the context. The endpoint
    enforces that — declaring it optional here keeps the actual
    ``actual``/``needs_review`` transitions concise.
    """

    status: KnowledgeStatusLiteral
    note: str | None = Field(default=None, max_length=1000)


# ── Responses ───────────────────────────────────────────────────────────


class MethodologyChunkOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    author_id: uuid.UUID | None
    title: str
    body: str
    kind: str
    tags: list[str]
    keywords: list[str]
    knowledge_status: str
    last_reviewed_at: datetime | None
    last_reviewed_by: uuid.UUID | None
    review_due_at: datetime | None
    embedding_pending: bool
    """``True`` when ``embedding`` is NULL — the row is saved but the
    live-backfill worker hasn't computed the vector yet. UI can show
    a small "indexing…" indicator instead of pretending the chunk is
    already searchable."""
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MethodologyChunkListOut(BaseModel):
    items: list[MethodologyChunkOut]
    total: int


__all__ = [
    "MethodologyChunkCreate",
    "MethodologyChunkUpdate",
    "MethodologyStatusUpdate",
    "MethodologyChunkOut",
    "MethodologyChunkListOut",
    "MethodologyKindLiteral",
    "KnowledgeStatusLiteral",
    "TITLE_MAX",
    "BODY_MIN",
    "BODY_MAX",
    "LIST_FIELD_MAX",
    "LIST_ITEM_MAX",
]
