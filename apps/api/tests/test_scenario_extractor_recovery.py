"""Tests for scenario_extractor.run_extraction db-level recovery
(SEC-2026-05-02 audit fix #10).

The post-classification block (db.add + flush + mark_scenario_draft_ready)
is now wrapped in try/except. If any DB-level failure happens between
``mark_scenario_draft_extracting`` and ``mark_scenario_draft_ready``,
the attachment is forced to ``classification_status="scenario_draft_failed"``
via a best-effort recovery write in a fresh session.

Without this, an attachment whose flush failed (UNIQUE conflict,
connection blip) sat in ``scenario_draft_extracting`` forever and the
re-extract endpoint refused to retry it.
"""

from __future__ import annotations

import inspect

import pytest


def test_run_extraction_wraps_post_flush_in_try_except():
    """Source-level check: the helper must contain a try/except wrapping
    db.flush + mark_scenario_draft_ready, plus a best-effort recovery
    write that flips classification_status back from extracting."""
    from app.services import scenario_extractor

    src = inspect.getsource(scenario_extractor.run_extraction)
    # The recovery branch must reference the failed state and rollback.
    assert "scenario_draft_failed" in src, (
        "run_extraction must mark attachment as scenario_draft_failed on "
        "post-flush DB failure (SEC-2026-05-02 audit fix #10)"
    )
    # Must use a fresh session for recovery so a poisoned `db` transaction
    # can't block the status flip.
    assert "async_session as _recovery_session_factory" in src, (
        "recovery must open a new DB session, not reuse the failing one"
    )
    # Defensive rollback before recovery.
    assert "await db.rollback()" in src, (
        "must roll back the in-memory transaction before the recovery write"
    )


def test_run_extraction_recovery_uses_idempotent_where_clause():
    """The recovery UPDATE must filter on
    ``classification_status == "scenario_draft_extracting"`` so it cannot
    accidentally overwrite a row that another worker has since
    transitioned to ready/failed."""
    from app.services import scenario_extractor

    src = inspect.getsource(scenario_extractor.run_extraction)
    # The where clause guards against double-flip.
    assert (
        '_Attachment.classification_status == "scenario_draft_extracting"' in src
    ), (
        "recovery UPDATE must be guarded by classification_status="
        "scenario_draft_extracting to stay idempotent under retries"
    )


def test_run_extraction_re_raises_on_failure():
    """After the recovery write, the original exception must re-raise so
    the caller (FastAPI endpoint) returns a 5xx and the FE can show a
    real error rather than a stuck spinner."""
    from app.services import scenario_extractor

    src = inspect.getsource(scenario_extractor.run_extraction)
    # The except block ends with `raise` (re-raise the original).
    # Look for `raise` AFTER the recovery write.
    idx = src.rfind("scenario_draft_failed")
    tail = src[idx:]
    assert "raise" in tail, (
        "run_extraction must re-raise the underlying exception after "
        "best-effort recovery — caller needs the 5xx signal"
    )
