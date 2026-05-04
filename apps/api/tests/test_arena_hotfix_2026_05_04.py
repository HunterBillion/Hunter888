"""Regression tests for the 2026-05-04 Arena hot-fix.

Each test pins one of the production bugs the role-by-role audit
caught with the four test creds against x-hunter.expert (prod sha
aa8ea5c) and the corresponding fix lands in the same PR.

  * Empty PUT used to wipe `fact_text` under a 200 OK
  * `extra` fields (`is_active` / `knowledge_status`) silently dropped
    while the response still claimed 200 "Updated"
  * Bad `category` value crashed at the DB layer with 500 instead of
    422 with a readable enum list
  * `content` alias used to slip past the create validator with no
    `min_length` / `max_length`
  * Diagnostics fields (`embedding_ready`, `retrieval_count`,
    `updated_at`) were missing from list-response so the FE couldn't
    flag "embedding pending" rows
"""
from __future__ import annotations

import pytest

from app.schemas.rop import (
    ArenaChunkCreateRequest,
    ArenaChunkResponse,
    ArenaChunkUpdateRequest,
)


# ── Empty / short fact_text now rejected on UPDATE ─────────────────────


def test_update_rejects_empty_fact_text():
    """Pre-fix: ``PUT {"fact_text": ""}`` returned 200 and wiped the
    chunk's text in DB (one of the live audit hits actually wrecked a
    real chunk and had to be restored from a JSON snapshot)."""
    with pytest.raises(Exception):
        ArenaChunkUpdateRequest.model_validate({"fact_text": ""})


def test_update_rejects_short_fact_text():
    with pytest.raises(Exception):
        ArenaChunkUpdateRequest.model_validate({"fact_text": "too short"})


def test_update_rejects_short_content_alias():
    """Same min_length applies to the legacy `content` alias — pre-fix
    only `fact_text` was bounded, so `PUT {"content": "ok"}` slipped."""
    with pytest.raises(Exception):
        ArenaChunkUpdateRequest.model_validate({"content": "ok"})


def test_update_rejects_oversize_fact_text():
    with pytest.raises(Exception):
        ArenaChunkUpdateRequest.model_validate({"fact_text": "x" * 20001})


# ── extra="forbid" closes the silent-no-op-200 bug ─────────────────────


def test_update_rejects_unknown_field_is_active():
    """Pre-fix: ``PUT {"is_active": false}`` → 200 "Updated" but the
    flag never reached the ORM. Operator believed the chunk was retired
    from RAG; AI kept serving it."""
    with pytest.raises(Exception):
        ArenaChunkUpdateRequest.model_validate({
            "is_active": False,
            "fact_text": "Минимальный порог долга — 500 000 рублей.",
        })


def test_update_rejects_unknown_field_knowledge_status():
    with pytest.raises(Exception):
        ArenaChunkUpdateRequest.model_validate({
            "knowledge_status": "outdated",
            "fact_text": "Минимальный порог долга — 500 000 рублей.",
        })


def test_create_rejects_unknown_field():
    with pytest.raises(Exception):
        ArenaChunkCreateRequest.model_validate({
            "fact_text": "Минимальный порог долга — 500 000 рублей.",
            "law_article": "Ст. 213.3",
            "category": "eligibility",
            "is_active": True,  # not in schema → must 422
        })


# ── category enum: 500 → 422 ──────────────────────────────────────────


def test_create_rejects_unknown_category():
    """Pre-fix: bad category passed Pydantic (`category: str`) and blew
    up at the Postgres enum cast → 500 generic. Now: 422 with the list
    of valid LegalCategory values in the error."""
    with pytest.raises(Exception):
        ArenaChunkCreateRequest.model_validate({
            "fact_text": "Минимальный порог долга — 500 000 рублей.",
            "law_article": "Ст. 213.3",
            "category": "audit-test",  # not a LegalCategory member
        })


def test_create_accepts_known_category():
    payload = ArenaChunkCreateRequest.model_validate({
        "fact_text": "Минимальный порог долга — 500 000 рублей.",
        "law_article": "Ст. 213.3",
        "category": "eligibility",
    })
    kwargs = payload.to_orm_kwargs()
    # Enum coerced to LegalCategory; ORM accepts the enum object.
    assert hasattr(kwargs["category"], "value")
    assert kwargs["category"].value == "eligibility"


def test_update_accepts_partial_no_category_change():
    """`category` is now an Enum but still optional — partial PATCH of
    just `tags` must NOT require category."""
    payload = ArenaChunkUpdateRequest.model_validate({
        "tags": ["обновлённый", "тег"],
    })
    kwargs = payload.to_orm_kwargs()
    assert "category" not in kwargs
    assert kwargs["tags"] == ["обновлённый", "тег"]


# ── Response shape: full fact_text + diagnostics ──────────────────────


def test_response_has_diagnostics_fields():
    """The list response now exposes embedding_ready / retrieval_count
    so the FE can render a chip on chunks that aren't yet RAG-ready."""
    fields = set(ArenaChunkResponse.model_fields.keys())
    assert {"embedding_ready", "retrieval_count", "updated_at"}.issubset(fields)


def test_response_fact_text_not_truncated_in_schema():
    """The response model itself doesn't enforce length — the API
    handler used to truncate manually to 200 chars. Pin: there's no
    max_length on `fact_text` in the response schema (truthy means the
    handler must hand over the whole string)."""
    field = ArenaChunkResponse.model_fields["fact_text"]
    metadata = list(getattr(field, "metadata", []) or [])
    # No MaxLen constraint should appear
    for m in metadata:
        cls_name = type(m).__name__.lower()
        assert "maxlen" not in cls_name, (
            f"fact_text response field has unexpected length cap: {m!r}"
        )
