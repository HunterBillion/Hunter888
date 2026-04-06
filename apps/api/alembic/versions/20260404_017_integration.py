"""Training-Arena integration: Hunter Score, cross-recommendations (DOC_14).

Revision ID: 20260404_017
Revises: 20260404_016
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260404_017"
down_revision = "20260404_016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Hunter Score fields on manager_progress
    op.add_column("manager_progress", sa.Column("hunter_score", sa.Float(), server_default="0.0", nullable=False))
    op.add_column("manager_progress", sa.Column("hunter_score_updated_at", sa.DateTime(timezone=True), nullable=True))

    # Archetype tracking in PvP duels (for cross-recommendations)
    op.add_column("pvp_duels", sa.Column("archetype_code", sa.String(64), nullable=True))

    # Cross-recommendation cache table
    op.create_table(
        "cross_recommendation_cache",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("recommendations", JSONB(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ttl_minutes", sa.Integer(), nullable=False, server_default="60"),
    )


def downgrade() -> None:
    op.drop_table("cross_recommendation_cache")
    op.drop_column("pvp_duels", "archetype_code")
    op.drop_column("manager_progress", "hunter_score_updated_at")
    op.drop_column("manager_progress", "hunter_score")
