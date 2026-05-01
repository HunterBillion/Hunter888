"""Tests for the arena_knowledge auto-publish gate (Content→Arena PR-3).

Locks in the security-critical contract:
* Auto-publish triggers ONLY on ``draft.original_confidence`` (immutable).
* The editable ``draft.confidence`` field is never consulted (post-hoc
  bump attack — see migration 20260429_002 audit-fix C7).
* NULL original_confidence falls through to the review queue.
* Threshold edge case: equality counts as auto-publish.
* Below threshold → ``is_active=False`` (legacy review-queue behaviour).

The HTTP endpoint is exercised via a direct function call rather than
the full ASGI app to keep tests focused on the gating logic; the request
shape and auth gate are covered by test_api_endpoints.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _draft(*, original_confidence, confidence=0.5, route_type="arena_knowledge", status="ready", extracted=None):
    d = MagicMock()
    d.id = uuid.uuid4()
    d.route_type = route_type
    d.status = status
    d.original_confidence = original_confidence
    d.confidence = confidence
    d.extracted = extracted or {
        "category": "general",
        "fact_text": "ст. 213.3 — порог банкротства",
        "law_article": "ст. 213.3",
    }
    return d


def _patched_db(draft):
    """Stub AsyncSession that returns ``draft`` from execute().scalar_one_or_none()."""
    db = MagicMock()
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=draft)
    db.execute = AsyncMock(return_value=res)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_high_original_confidence_auto_publishes():
    """original_confidence above threshold → is_active=True + 'auto_published' tag."""
    from app.api.rop import approve_arena_knowledge_draft

    draft = _draft(original_confidence=0.95, confidence=0.5)
    db = _patched_db(draft)

    captured: list = []

    def _capture_add(obj):
        captured.append(obj)

    db.add = _capture_add

    request = MagicMock()
    user = MagicMock()

    with patch("app.config.settings.arena_knowledge_auto_publish_confidence", 0.85):
        result = await approve_arena_knowledge_draft(
            request=request, draft_id=draft.id, user=user, db=db,
        )

    # The chunk was added to the session
    chunks = [o for o in captured if hasattr(o, "is_active")]
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.is_active is True
    assert "auto_published" in chunk.tags
    # Response surfaces the decision so FE can render the right toast
    assert result["auto_published"] is True
    assert result["original_confidence"] == 0.95


@pytest.mark.asyncio
async def test_low_original_confidence_falls_to_review_queue():
    from app.api.rop import approve_arena_knowledge_draft

    draft = _draft(original_confidence=0.55, confidence=0.99)  # editable bumped, original low
    db = _patched_db(draft)

    captured: list = []
    db.add = lambda o: captured.append(o)

    with patch("app.config.settings.arena_knowledge_auto_publish_confidence", 0.85):
        result = await approve_arena_knowledge_draft(
            request=MagicMock(), draft_id=draft.id, user=MagicMock(), db=db,
        )

    chunks = [o for o in captured if hasattr(o, "is_active")]
    assert chunks[0].is_active is False
    assert "auto_published" not in chunks[0].tags
    assert result["auto_published"] is False


@pytest.mark.asyncio
async def test_post_hoc_confidence_bump_does_not_auto_publish():
    """The C7 audit-fix scenario: ROP raises ``confidence`` to 0.99 hoping
    to ride the fast-track. ``original_confidence`` (LLM's number) stays
    low, so the gate REJECTS auto-publish. This is the security property
    we lock in here.
    """
    from app.api.rop import approve_arena_knowledge_draft

    draft = _draft(original_confidence=0.40, confidence=0.99)  # bumped post-extract
    db = _patched_db(draft)
    captured: list = []
    db.add = lambda o: captured.append(o)

    with patch("app.config.settings.arena_knowledge_auto_publish_confidence", 0.85):
        result = await approve_arena_knowledge_draft(
            request=MagicMock(), draft_id=draft.id, user=MagicMock(), db=db,
        )

    chunk = [o for o in captured if hasattr(o, "is_active")][0]
    assert chunk.is_active is False, "post-hoc confidence bump must NOT auto-publish"
    assert result["auto_published"] is False


@pytest.mark.asyncio
async def test_null_original_confidence_falls_to_review_queue():
    """Legacy PR-1 rows have NULL original_confidence — treat as below."""
    from app.api.rop import approve_arena_knowledge_draft

    draft = _draft(original_confidence=None, confidence=0.99)
    db = _patched_db(draft)
    captured: list = []
    db.add = lambda o: captured.append(o)

    with patch("app.config.settings.arena_knowledge_auto_publish_confidence", 0.85):
        result = await approve_arena_knowledge_draft(
            request=MagicMock(), draft_id=draft.id, user=MagicMock(), db=db,
        )

    chunk = [o for o in captured if hasattr(o, "is_active")][0]
    assert chunk.is_active is False
    assert result["auto_published"] is False
    assert result["original_confidence"] is None


@pytest.mark.asyncio
async def test_exact_threshold_counts_as_auto_publish():
    """Equality with the threshold publishes. Documented behaviour for
    operators tuning the value — '0.85' means '0.85 and above'."""
    from app.api.rop import approve_arena_knowledge_draft

    draft = _draft(original_confidence=0.85)
    db = _patched_db(draft)
    captured: list = []
    db.add = lambda o: captured.append(o)

    with patch("app.config.settings.arena_knowledge_auto_publish_confidence", 0.85):
        result = await approve_arena_knowledge_draft(
            request=MagicMock(), draft_id=draft.id, user=MagicMock(), db=db,
        )

    chunk = [o for o in captured if hasattr(o, "is_active")][0]
    assert chunk.is_active is True
    assert result["auto_published"] is True
