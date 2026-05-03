"""quiz_v2_answer_keys table — Path A grader storage.

Revision ID: 20260503_001
Revises: 20260502_010
Create Date: 2026-05-03

Why this exists
---------------

Path A redesigns the knowledge-quiz arena to grade answers
deterministically against a pre-computed answer key (Kahoot/Quizizz
pattern) instead of streaming a verdict from an LLM. Design doc:
``docs/QUIZ_V2_ARENA_DESIGN.md``.

This migration creates the ``quiz_v2_answer_keys`` table that backs the
deterministic grader.

Schema decisions (cross-references in design-doc §6 + §9)
---------------------------------------------------------

* ``team_id`` is **nullable** — Q-NEW-4 decision: global baseline +
  optional per-team override. Lookup precedence at grade time:
  team-specific row first, then ``team_id IS NULL`` global row.
* ``UNIQUE (chunk_id, question_hash, team_id)`` — Postgres treats NULL
  as distinct, so a team can override a global key for the same
  ``(chunk_id, question_hash)`` pair.
* ``flavor IN ('factoid', 'strategic')`` — Q-NEW-3 decision. Factoid
  rows take ``expected_answer = chunk.fact_text`` directly (no LLM
  needed at backfill); strategic rows are LLM-generated.
* ``knowledge_status / is_active / source / original_confidence`` mirror
  ``legal_knowledge_chunks`` so the existing
  ``knowledge_review_policy.mark_reviewed`` state machine and the
  ``KnowledgeReviewQueue`` UI can be reused without copy.
* ``original_confidence`` is immutable post-insert (anti-tamper, same
  rationale as ``arena_knowledge_auto_publish_confidence`` gate at
  ``api/rop.py:1683``). The LLM extractor writes it once; reviewers can
  flip ``knowledge_status`` but not ``original_confidence``.

Backfill
--------

This migration creates the table only. The 375-chunk LLM backfill is
performed by ``scripts/quiz_v2_backfill_answer_keys.py`` as a separate
ops step, run **after** the migration ships and the worker has the
config it needs. Backfill writes rows with ``is_active=False`` and
``knowledge_status='needs_review'``; rows with
``original_confidence >= 0.85`` auto-publish via the gate in the
backfill script (matches the existing arena-knowledge pattern).

Rollback
--------

Drop the table. No data dependencies in either direction yet — A4 is
when ``ws/knowledge.py`` starts reading from this table.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260503_001"
down_revision: Union[str, Sequence[str], None] = "20260502_010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quiz_v2_answer_keys",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "chunk_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_knowledge_chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=True,
            comment="NULL = global baseline; non-NULL = per-team override",
        ),
        sa.Column("question_hash", sa.String(length=32), nullable=False),
        sa.Column("flavor", sa.String(length=16), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("match_strategy", sa.String(length=16), nullable=False),
        sa.Column(
            "match_config",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "synonyms",
            sa.dialects.postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("article_ref", sa.String(length=128), nullable=True),
        sa.Column(
            "knowledge_status",
            sa.String(length=16),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("original_confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("generated_by", sa.String(length=64), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "reviewed_by",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "flavor IN ('factoid', 'strategic')",
            name="ck_quiz_v2_answer_keys_flavor",
        ),
        sa.CheckConstraint(
            "match_strategy IN ('exact', 'synonyms', 'regex', 'keyword', 'embedding')",
            name="ck_quiz_v2_answer_keys_match_strategy",
        ),
        sa.CheckConstraint(
            "knowledge_status IN ('actual', 'disputed', 'outdated', 'needs_review')",
            name="ck_quiz_v2_answer_keys_status",
        ),
        sa.CheckConstraint(
            "source IN ('llm_backfill', 'admin_editor', 'seed_loader')",
            name="ck_quiz_v2_answer_keys_source",
        ),
        sa.CheckConstraint(
            "original_confidence IS NULL OR (original_confidence >= 0 AND original_confidence <= 1)",
            name="ck_quiz_v2_answer_keys_confidence_bounds",
        ),
        sa.UniqueConstraint(
            "chunk_id",
            "question_hash",
            "team_id",
            name="uq_quiz_v2_answer_keys_chunk_hash_team",
        ),
    )

    op.create_index(
        "ix_quiz_v2_answer_keys_lookup",
        "quiz_v2_answer_keys",
        ["chunk_id", "question_hash", "team_id"],
    )
    op.create_index(
        "ix_quiz_v2_answer_keys_chunk",
        "quiz_v2_answer_keys",
        ["chunk_id"],
    )
    op.create_index(
        "ix_quiz_v2_answer_keys_review_queue",
        "quiz_v2_answer_keys",
        ["knowledge_status"],
        postgresql_where=sa.text("is_active = false"),
    )


def downgrade() -> None:
    op.drop_index("ix_quiz_v2_answer_keys_review_queue", table_name="quiz_v2_answer_keys")
    op.drop_index("ix_quiz_v2_answer_keys_chunk", table_name="quiz_v2_answer_keys")
    op.drop_index("ix_quiz_v2_answer_keys_lookup", table_name="quiz_v2_answer_keys")
    op.drop_table("quiz_v2_answer_keys")
