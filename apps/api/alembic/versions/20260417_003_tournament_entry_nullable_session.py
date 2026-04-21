"""tournament_entries.session_id → nullable (unified TP entries don't pin to one session).

Revision ID: 20260417_003
Revises: 20260417_002
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260417_003"
down_revision: Union[str, None] = "20260417_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("tournament_entries", "session_id", nullable=True)


def downgrade() -> None:
    op.alter_column("tournament_entries", "session_id", nullable=False)
