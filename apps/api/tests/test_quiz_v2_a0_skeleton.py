"""Smoke tests for quiz_v2 A0 skeleton (Path A).

Locks in the public surface:
* Three new feature flags exist on ``settings`` and default OFF / empty.
* ``is_quiz_v2_grader_enabled_for_user`` honors master flag and whitelist
  override correctly (whitelist wins even when master is False).
* ``new_answer_id`` returns a fresh hex UUID v4 each call.
* ``question_hash`` produces stable md5 matching the design-doc shape.
* The skeleton modules raise ``NotImplementedError`` from the
  not-yet-built entry points so call-sites fail loudly on flag flip.

These tests are intentionally cheap — A0 is scaffolding only. A2/A3/A4
add the real behavioral tests as their PRs land.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.config import settings
from app.services.quiz_v2 import (
    AnswerKey,
    is_quiz_v2_grader_enabled_for_user,
    new_answer_id,
    question_hash,
)
from app.services.quiz_v2 import answer_keys as answer_keys_mod
from app.services.quiz_v2 import events as events_mod
from app.services.quiz_v2 import grader as grader_mod


# ─── Feature flags ────────────────────────────────────────────────────


def test_quiz_v2_grader_master_flag_defaults_off():
    """Master flag MUST default to False so a fresh deploy is dormant."""
    assert settings.quiz_v2_grader_enabled is False


def test_quiz_v2_grader_user_whitelist_defaults_empty():
    """Whitelist MUST default to empty list so no user is opted-in by accident."""
    assert settings.quiz_v2_grader_user_whitelist == []


def test_quiz_v2_answer_key_auto_publish_threshold_matches_arena_pattern():
    """Match the ``arena_knowledge_auto_publish_confidence`` precedent (0.85)."""
    assert settings.quiz_v2_answer_key_auto_publish_confidence == 0.85


# ─── Rollout gate ─────────────────────────────────────────────────────


def test_rollout_gate_off_when_master_off_and_user_not_whitelisted(monkeypatch):
    monkeypatch.setattr(settings, "quiz_v2_grader_enabled", False)
    monkeypatch.setattr(settings, "quiz_v2_grader_user_whitelist", [])
    assert is_quiz_v2_grader_enabled_for_user("user-abc") is False
    assert is_quiz_v2_grader_enabled_for_user(None) is False


def test_rollout_gate_on_when_master_on(monkeypatch):
    monkeypatch.setattr(settings, "quiz_v2_grader_enabled", True)
    monkeypatch.setattr(settings, "quiz_v2_grader_user_whitelist", [])
    assert is_quiz_v2_grader_enabled_for_user("user-abc") is True
    assert is_quiz_v2_grader_enabled_for_user(None) is True


def test_rollout_gate_whitelist_overrides_master_off(monkeypatch):
    """Whitelisted user MUST get v2 even when the master flag is False."""
    monkeypatch.setattr(settings, "quiz_v2_grader_enabled", False)
    monkeypatch.setattr(settings, "quiz_v2_grader_user_whitelist", ["user-author"])
    assert is_quiz_v2_grader_enabled_for_user("user-author") is True
    assert is_quiz_v2_grader_enabled_for_user("user-other") is False


def test_rollout_gate_anonymous_user_ignores_whitelist(monkeypatch):
    """``user_id=None`` honors master flag only — never the whitelist."""
    monkeypatch.setattr(settings, "quiz_v2_grader_enabled", False)
    monkeypatch.setattr(settings, "quiz_v2_grader_user_whitelist", ["user-author"])
    assert is_quiz_v2_grader_enabled_for_user(None) is False


# ─── ID + hash helpers ────────────────────────────────────────────────


def test_new_answer_id_is_uuid_hex():
    aid = new_answer_id()
    # Must round-trip through uuid.UUID — proves it is a valid v4 hex.
    parsed = uuid.UUID(hex=aid)
    assert parsed.version == 4


def test_new_answer_id_is_unique():
    ids = {new_answer_id() for _ in range(50)}
    assert len(ids) == 50, "answer_id collisions in 50 calls — RNG broken"


def test_question_hash_matches_design_doc_shape():
    """``md5(question_text + "::" + canonical_answer)`` — 32-char hex."""
    q = "Может ли управляющий забрать бытовую технику из квартиры?"
    a = "Нет, бытовая техника защищена ст. 446 ГПК."
    h = question_hash(q, a)
    expected = hashlib.md5(f"{q}::{a}".encode("utf-8")).hexdigest()
    assert h == expected
    assert len(h) == 32
    assert all(c in "0123456789abcdef" for c in h)


def test_question_hash_is_stable_and_deterministic():
    h1 = question_hash("q", "a")
    h2 = question_hash("q", "a")
    assert h1 == h2


# ─── Skeleton entry points raise NotImplementedError ──────────────────


@pytest.mark.asyncio
async def test_grade_answer_skeleton_raises():
    with pytest.raises(NotImplementedError, match="A0 skeleton"):
        await grader_mod.grade_answer(
            answer_id="aid",
            question_id="qid",
            submitted_text="text",
            chunk_id="cid",
            team_id=None,
        )


@pytest.mark.asyncio
async def test_load_answer_key_skeleton_raises():
    with pytest.raises(NotImplementedError, match="A0 skeleton"):
        await answer_keys_mod.load_answer_key(
            chunk_id="cid",
            question_hash="h" * 32,
            team_id=None,
        )


@pytest.mark.asyncio
async def test_publish_verdict_skeleton_raises():
    with pytest.raises(NotImplementedError, match="A0 skeleton"):
        await events_mod.publish_verdict(correlation_id="cid", payload={})


# ─── AnswerKey dataclass shape ────────────────────────────────────────


def test_answer_key_dataclass_fields():
    """Lock the field set so future PRs can't drift the wire shape silently."""
    key = AnswerKey(
        id="id",
        chunk_id="cid",
        team_id=None,
        question_hash="h" * 32,
        flavor="factoid",
        expected_answer="ans",
        match_strategy="exact",
        match_config={},
        synonyms=[],
        article_ref=None,
        knowledge_status="actual",
        is_active=True,
    )
    assert key.flavor in ("factoid", "strategic")
    assert key.match_strategy in ("exact", "synonyms", "regex", "keyword", "embedding")
