"""Restore review moderation flag after incomplete deleted-only refactor.

Revision ID: 20260424_001
Revises: reviews_use_deleted
Create Date: 2026-04-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260424_001"
down_revision: Union[str, Sequence[str], None] = "reviews_use_deleted"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table_name AND column_name = :column_name"
    ), {"table_name": table_name, "column_name": column_name}).fetchone())


def upgrade() -> None:
    if not _column_exists("reviews", "approved"):
        op.add_column(
            "reviews",
            sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )

    # Existing visible reviews stay visible; hidden rows stay hidden.
    op.execute("UPDATE reviews SET approved = CASE WHEN deleted = true THEN false ELSE true END")


def downgrade() -> None:
    if _column_exists("reviews", "approved"):
        op.drop_column("reviews", "approved")
