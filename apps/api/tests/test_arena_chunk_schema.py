"""TZ-3 §12.2 — pure-function tests for the new ArenaChunk Pydantic schemas.

The handler in `apps/api/app/api/rop.py:create_chunk/update_chunk`
delegates to `ArenaChunkCreateRequest.to_orm_kwargs()` /
`ArenaChunkUpdateRequest.to_orm_kwargs()`. These tests pin the
alias-resolution rules so a future "let's drop the legacy aliases"
refactor doesn't silently break the FE that's still sending them.
"""

from __future__ import annotations

import pytest

from app.schemas.rop import (
    ArenaChunkCreateRequest,
    ArenaChunkUpdateRequest,
)


# ── Create — canonical-only ──────────────────────────────────────────────────


def test_create_with_canonical_names_only():
    payload = ArenaChunkCreateRequest.model_validate({
        "fact_text": "Минимальный порог долга — 500 000 рублей.",
        "law_article": "Ст. 213.3",
        "category": "eligibility",
        "tags": ["порог", "критерий"],
    })
    kwargs = payload.to_orm_kwargs()
    assert kwargs["fact_text"] == "Минимальный порог долга — 500 000 рублей."
    assert kwargs["law_article"] == "Ст. 213.3"
    # No drift names leak through
    assert "title" not in kwargs
    assert "content" not in kwargs
    assert "article_reference" not in kwargs


# ── Create — alias resolution ───────────────────────────────────────────────


def test_create_falls_back_from_content_to_fact_text():
    """Legacy FE sends `content` — backend folds into `fact_text`."""
    payload = ArenaChunkCreateRequest.model_validate({
        "title": "Ст. 213.3",
        "content": "Текст факта.",
        "category": "eligibility",
    })
    kwargs = payload.to_orm_kwargs()
    assert kwargs["fact_text"] == "Текст факта."
    assert kwargs["law_article"] == "Ст. 213.3"


def test_create_canonical_wins_over_alias():
    """If both canonical and alias are present, canonical takes priority."""
    payload = ArenaChunkCreateRequest.model_validate({
        "fact_text": "canonical fact",
        "content": "legacy alias should be ignored",
        "law_article": "canonical article",
        "title": "legacy title",
        "article_reference": "legacy article ref",
        "category": "eligibility",
    })
    kwargs = payload.to_orm_kwargs()
    assert kwargs["fact_text"] == "canonical fact"
    assert kwargs["law_article"] == "canonical article"


def test_create_article_reference_alias_wins_over_title():
    """When `law_article` absent: `article_reference` > `title` for the
    `law_article` slot — `title` is just a UI label, the article ref
    is the actual law citation."""
    payload = ArenaChunkCreateRequest.model_validate({
        "fact_text": "Текст факта длиной более 10 символов.",
        "title": "UI title",
        "article_reference": "Ст. 213.3",
        "category": "eligibility",
    })
    kwargs = payload.to_orm_kwargs()
    assert kwargs["law_article"] == "Ст. 213.3"


def test_create_raises_when_no_fact_or_content():
    payload = ArenaChunkCreateRequest.model_validate({
        "law_article": "Ст. 213.3",
        "category": "eligibility",
    })
    with pytest.raises(ValueError, match="fact_text"):
        payload.to_orm_kwargs()


def test_create_raises_when_no_article_anywhere():
    payload = ArenaChunkCreateRequest.model_validate({
        "fact_text": "Текст факта.",
        "category": "eligibility",
    })
    with pytest.raises(ValueError, match="law_article"):
        payload.to_orm_kwargs()


# ── Update — partial ────────────────────────────────────────────────────────


def test_update_only_emits_supplied_fields():
    """Partial update — fields NOT supplied must NOT appear in the
    output dict (otherwise we'd zero-out columns the caller didn't
    mean to touch)."""
    payload = ArenaChunkUpdateRequest.model_validate({
        "fact_text": "новый текст",
    })
    kwargs = payload.to_orm_kwargs()
    assert kwargs == {"fact_text": "новый текст"}


def test_update_alias_only_still_writes_canonical():
    """If FE sends `content` only, ORM update still hits `fact_text`."""
    payload = ArenaChunkUpdateRequest.model_validate({
        "content": "обновлённый",
    })
    kwargs = payload.to_orm_kwargs()
    assert kwargs == {"fact_text": "обновлённый"}


def test_update_with_no_fields_returns_empty_dict():
    """Empty update — caller gets empty dict, can decide to noop or
    422. Schema doesn't enforce non-empty."""
    payload = ArenaChunkUpdateRequest.model_validate({})
    assert payload.to_orm_kwargs() == {}


def test_update_drift_aliases_resolve_to_canonical_targets():
    payload = ArenaChunkUpdateRequest.model_validate({
        "title": "новый заголовок",
        "article_reference": "Ст. 213.5",
    })
    kwargs = payload.to_orm_kwargs()
    # title or article_reference both target law_article;
    # article_reference wins.
    assert kwargs.get("law_article") == "Ст. 213.5"


# ── Negative space — schema rejects nonsense values ─────────────────────────


def test_create_rejects_difficulty_out_of_range():
    with pytest.raises(Exception):  # noqa: B017 — ValidationError
        ArenaChunkCreateRequest.model_validate({
            "fact_text": "x" * 20,
            "law_article": "Ст. X",
            "category": "eligibility",
            "difficulty_level": 99,
        })


def test_create_rejects_too_short_fact_text():
    with pytest.raises(Exception):  # noqa: B017
        ArenaChunkCreateRequest.model_validate({
            "fact_text": "short",  # < 10 chars triggers min_length
            "law_article": "Ст. X",
            "category": "eligibility",
        })
