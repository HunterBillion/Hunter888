"""Unified tournament economy: rating_contributions + tournament columns.

- Creates rating_contributions (TP ledger for all activities).
- Makes tournaments.scenario_id nullable (mixed tournaments don't pin to one scenario).
- Adds tournaments.score_source (which activity sources count).
- Adds tournaments.auto_created (cron vs admin origin).

Revision ID: 20260417_002
Revises: 20260417_001
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260417_002"
down_revision: Union[str, None] = "20260417_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RATING_SOURCE_ENUM = sa.Enum(
    "training", "pvp", "knowledge", "story",
    name="rating_source",
)


def upgrade() -> None:
    # 1) rating_contributions table — idempotent enum creation
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rating_source') THEN
                CREATE TYPE rating_source AS ENUM ('training', 'pvp', 'knowledge', 'story');
            END IF;
        END $$;
    """)
    rating_source_col = postgresql.ENUM(
        "training", "pvp", "knowledge", "story",
        name="rating_source", create_type=False,
    )

    op.create_table(
        "rating_contributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", rating_source_col, nullable=False),
        sa.Column("source_ref_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("week_start", sa.Date, nullable=False),
        sa.Column(
            "earned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "tournament_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tournaments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.UniqueConstraint("source", "source_ref_id", name="uq_rating_contrib_source"),
    )
    op.create_index(
        "ix_rating_contributions_user_id", "rating_contributions", ["user_id"],
    )
    op.create_index(
        "ix_rating_contributions_week_start", "rating_contributions", ["week_start"],
    )
    op.create_index(
        "ix_rating_contributions_earned_at", "rating_contributions", ["earned_at"],
    )
    op.create_index(
        "ix_rating_contributions_tournament_id", "rating_contributions", ["tournament_id"],
    )
    op.create_index(
        "ix_rating_contrib_user_week", "rating_contributions", ["user_id", "week_start"],
    )

    # 2) tournaments — relax scenario_id NOT NULL
    op.alter_column("tournaments", "scenario_id", nullable=True)

    # 3) tournaments — add score_source + auto_created
    op.add_column(
        "tournaments",
        sa.Column(
            "score_source",
            sa.String(16),
            server_default="mixed",
            nullable=False,
        ),
    )
    op.add_column(
        "tournaments",
        sa.Column(
            "auto_created",
            sa.Boolean,
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tournaments", "auto_created")
    op.drop_column("tournaments", "score_source")
    op.alter_column("tournaments", "scenario_id", nullable=False)

    op.drop_index("ix_rating_contrib_user_week", table_name="rating_contributions")
    op.drop_index("ix_rating_contributions_tournament_id", table_name="rating_contributions")
    op.drop_index("ix_rating_contributions_earned_at", table_name="rating_contributions")
    op.drop_index("ix_rating_contributions_week_start", table_name="rating_contributions")
    op.drop_index("ix_rating_contributions_user_id", table_name="rating_contributions")
    op.drop_table("rating_contributions")

    RATING_SOURCE_ENUM.drop(op.get_bind(), checkfirst=True)
