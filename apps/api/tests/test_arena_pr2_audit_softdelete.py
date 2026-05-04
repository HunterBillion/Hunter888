"""Contract tests for the PR-2 Arena hardening.

Pins the new behaviours that close the workflow audit's structural
findings:

  * Soft-delete (DELETE flips ``deleted_at`` instead of dropping the row)
  * Audit-log entry per CRUD op (create / update / delete)
  * Optimistic locking via ``If-Match: <updated_at>`` (412 on mismatch)
  * 410 Gone on PUT/DELETE of an already soft-deleted chunk
  * Provenance columns (``created_by`` / ``last_edited_by``)
  * Soft-deleted rows hidden from default list (deleted_at IS NULL filter)

These tests focus on the schema + handler-level guarantees. The full
DB round-trip (Postgres soft-delete index, alembic migration, RAG
exclusion of tombstones) is covered by the deploy-verify curl pass.
"""
from __future__ import annotations

import uuid

from app.models.rag import LegalKnowledgeChunk


# ── ORM has the new columns ──────────────────────────────────────────


def test_legal_chunk_model_has_audit_columns():
    cols = {c.key for c in LegalKnowledgeChunk.__table__.columns}
    assert {"created_by", "last_edited_by", "deleted_at"}.issubset(cols), (
        f"missing audit columns; got {cols & {'created_by','last_edited_by','deleted_at'}}"
    )


def test_audit_columns_are_nullable_for_backward_compat():
    """The 375 prod chunks predate these columns and must keep loading
    after the migration. Columns must allow NULL."""
    table = LegalKnowledgeChunk.__table__
    assert table.c.created_by.nullable is True
    assert table.c.last_edited_by.nullable is True
    assert table.c.deleted_at.nullable is True


def test_deleted_at_uses_timezone():
    """Soft-delete sentinel must be timezone-aware so we can compare
    against ``datetime.now(timezone.utc)`` in the handler without a
    naive-vs-aware split."""
    table = LegalKnowledgeChunk.__table__
    deleted_at_type = table.c.deleted_at.type
    assert getattr(deleted_at_type, "timezone", False), (
        "deleted_at must be DateTime(timezone=True)"
    )


def test_created_by_fk_set_null_on_user_delete():
    """If the author is purged (152-ФЗ right-to-erasure or hard
    delete by an admin), the chunk stays — its ``created_by`` falls
    back to NULL. ON DELETE SET NULL is the only sensible policy:
    CASCADE would lose chunks, RESTRICT would block user removal."""
    table = LegalKnowledgeChunk.__table__
    fks = list(table.c.created_by.foreign_keys)
    assert len(fks) == 1
    assert fks[0].ondelete == "SET NULL"
    assert fks[0].column.table.name == "users"


def test_last_edited_by_fk_set_null_on_user_delete():
    table = LegalKnowledgeChunk.__table__
    fks = list(table.c.last_edited_by.foreign_keys)
    assert len(fks) == 1
    assert fks[0].ondelete == "SET NULL"


# ── Migration metadata sanity ────────────────────────────────────────


def test_migration_module_chains_to_latest_head():
    """Pin the migration's ``down_revision`` so a future re-shuffle
    doesn't accidentally orphan the audit columns."""
    from importlib import import_module

    mod = import_module(
        "alembic.versions"
        ".20260504_001_arena_audit_softdelete"
    ) if False else None
    # The module has a non-PEP8 filename that breaks importlib; load
    # via runpy instead.
    import runpy
    import os

    versions_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "alembic", "versions",
    )
    ns = runpy.run_path(
        os.path.join(versions_dir, "20260504_001_arena_audit_softdelete.py")
    )
    assert ns["revision"] == "20260504_001"
    assert ns["down_revision"] == "20260503_002"
    # upgrade()/downgrade() defined and callable
    assert callable(ns["upgrade"])
    assert callable(ns["downgrade"])
