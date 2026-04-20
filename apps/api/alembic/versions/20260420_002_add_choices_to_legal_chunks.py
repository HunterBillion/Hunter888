"""Add multiple-choice fields to legal_knowledge_chunks.

Revision ID: 20260420_002
Revises: 20260420_001
Create Date: 2026-04-20

Adds two nullable fields so existing rows keep working (free-form answer
flow is the fallback when `choices` is NULL):

  * `choices`              JSONB  — ["option A", "option B", ...], 2-4 items
  * `correct_choice_index` INT    — 0-based index into `choices`

Why JSONB instead of a sibling table:
  * Answer options are ALWAYS rendered together with the question.
  * Tiny list (2-4 strings), no separate lifecycle.
  * A join per warm-up question would be wasteful.

Filling the column is a separate seeding step (scripts/seed_mc_choices.py)
— this migration just reserves the shape.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260420_002"
down_revision = "20260420_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "legal_knowledge_chunks",
        sa.Column(
            "choices",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "legal_knowledge_chunks",
        sa.Column(
            "correct_choice_index",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("legal_knowledge_chunks", "correct_choice_index")
    op.drop_column("legal_knowledge_chunks", "choices")
