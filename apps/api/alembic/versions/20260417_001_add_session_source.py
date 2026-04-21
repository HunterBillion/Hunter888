"""Add source column to training_sessions.

Tracks where a session was started from: "home", "training", "story".
Used for home client rotation flow and CRM integration.

Revision ID: 20260417_001
Revises: 20260415_006
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260417_001"
down_revision: Union[str, None] = "20260415_006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "training_sessions",
        sa.Column("source", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("training_sessions", "source")
