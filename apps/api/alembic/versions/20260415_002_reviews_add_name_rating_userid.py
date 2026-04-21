"""Add name, rating, user_id columns to reviews table.

Revision ID: 20260415_002
Revises: 20260415_001
Create Date: 2026-04-15
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260415_002"
down_revision: Union[str, None] = "20260415_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("name", sa.String(200), nullable=False, server_default=""))
    op.add_column("reviews", sa.Column("rating", sa.Integer(), nullable=False, server_default="5"))
    op.add_column(
        "reviews",
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("reviews", "user_id")
    op.drop_column("reviews", "rating")
    op.drop_column("reviews", "name")
