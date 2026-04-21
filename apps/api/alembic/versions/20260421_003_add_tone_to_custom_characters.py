"""Add tone column to custom_characters + merge three dangling heads.

Revision ID: 20260421_003
Revises: 20260421_002, 20260417_005, 20260402_004a
Create Date: 2026-04-21

Constructor v2 tone system (harsh / neutral / lively / friendly):
- CustomCharacter.tone nullable String(20) — null = archetype default.
- Also serves as a merge point for the three heads that had accumulated
  during April 2026 development (email verification, embedding v2 legal
  knowledge, missing-tables backfill). No destructive change; only an
  ALTER TABLE ADD COLUMN and a multi-parent revision link.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "20260421_003"
down_revision: Union[str, Sequence[str], None] = (
    "20260421_002",
    "20260417_005",
    "20260402_004a",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent check — if someone manually added the column already (or
    # this migration is replayed in dev), don't crash the apply.
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'custom_characters' AND column_name = 'tone'"
        )
    ).fetchone()
    if not exists:
        op.add_column(
            "custom_characters",
            sa.Column("tone", sa.String(length=20), nullable=True),
        )


def downgrade() -> None:
    # Safe: other features don't read tone — removing the column only
    # erases explicit user preferences and falls back to archetype defaults.
    with op.batch_alter_table("custom_characters") as batch_op:
        batch_op.drop_column("tone")
