"""Add push_subscriptions table for Web Push (Task X6).

Revision ID: 20260320_004
Revises: 20260320_003
Create Date: 2026-03-20
"""
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision: str = "20260320_004"
down_revision: Union[str, None] = "20260320_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("idx_push_sub_user_id", "push_subscriptions", ["user_id"])
    op.create_index(
        "idx_push_sub_user_endpoint",
        "push_subscriptions",
        ["user_id", "endpoint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_push_sub_user_endpoint", table_name="push_subscriptions")
    op.drop_index("idx_push_sub_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
