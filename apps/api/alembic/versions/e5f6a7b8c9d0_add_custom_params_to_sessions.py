"""Add custom_params JSONB to training_sessions.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_sessions",
        sa.Column("custom_params", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("training_sessions", "custom_params")
