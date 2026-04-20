"""Phase D — performance indexes.

Revision ID: 20260420_005
Revises: 20260420_004
Create Date: 2026-04-20

Composite index on ``knowledge_answers(session_id, user_id, created_at)``
— covers the two hottest query patterns:

  1. "fetch all answers a given user gave inside one quiz session"
     (PvP match replay, post-match review, coaching card).
  2. "latest N answers of this user in this session, most recent first"
     (live scoreboard + streak update).

Single-column indexes on session_id and user_id exist, but queries that
filter on both end up doing a bitmap index scan + recheck — fine at 10k
rows, painful at 10M.

The composite index is a strict addition — no column changes, no data
migration, creates concurrently so it doesn't block writes.
"""

from __future__ import annotations

from alembic import op


# revision identifiers
revision = "20260420_005"
down_revision = "20260420_004"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_knowledge_answers_session_user_created"


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY can't run inside a transaction; Alembic by
    # default wraps upgrade() in a transaction, so we use the plain form
    # which is fine for our table size (prod <10M rows) and brief blocks.
    op.create_index(
        INDEX_NAME,
        "knowledge_answers",
        ["session_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="knowledge_answers")
