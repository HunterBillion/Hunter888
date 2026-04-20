"""Add morning_drill_sessions table.

Revision ID: 20260420_001
Revises: 20260419_003
Create Date: 2026-04-20

Stores completed morning warm-ups so that:
  1. Daily goal `daily_warmup` can count them (user_id + date index).
  2. Streak / analytics services can query past runs (user_id + completed_at).
  3. Post-session review screen can show which questions were wrong
     (answers JSONB holds per-question records).

The `drill_session_id` column is the opaque string returned by
`GET /morning-drill` — we keep it for debugging but DON'T use it as PK:
it's generated client-side each request and is not authoritative.

Atomic completion: one row is INSERTed from POST /morning-drill/complete.
No partial state is persisted. This keeps the table small and semantics
simple (row exists ⇒ user finished a warm-up).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_001"
down_revision = "20260419_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "morning_drill_sessions",
        # PK default is python-side (uuid.uuid4) via the ORM. We deliberately
        # don't use server_default=gen_random_uuid() so the migration doesn't
        # require pgcrypto — every insert goes through SQLAlchemy anyway.
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("drill_session_id", sa.String(length=64), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False, server_default="0"),
        # Per-question records: [{question_id, kind, answer, ok, matched_keywords}]
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # date = date(completed_at in UTC); populated by app on INSERT so
        # Postgres doesn't have to compute timezone conversions at query time.
        sa.Column("date", sa.Date(), nullable=False),
    )

    # (user_id, date) — for the `daily_warmup` goal lookup (was the warm-up
    # finished today by this user?). Composite + non-unique since a user
    # MAY complete multiple warm-ups per day (e.g. demo reset in future).
    op.create_index(
        "ix_morning_drill_sessions_user_date",
        "morning_drill_sessions",
        ["user_id", "date"],
    )

    # (user_id, completed_at DESC) — for streak / history queries.
    op.create_index(
        "ix_morning_drill_sessions_user_completed",
        "morning_drill_sessions",
        ["user_id", sa.text("completed_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_morning_drill_sessions_user_completed",
        table_name="morning_drill_sessions",
    )
    op.drop_index(
        "ix_morning_drill_sessions_user_date",
        table_name="morning_drill_sessions",
    )
    op.drop_table("morning_drill_sessions")
