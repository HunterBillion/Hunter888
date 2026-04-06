"""Expand achievement system: 35→140, 8 categories, secret/anti support (DOC_07).

Revision ID: 20260404_010
Revises: 20260404_009
Create Date: 2026-04-04

Adds hint, is_secret, is_anti, recommendation columns.
Updates category constraint for 8 categories.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260404_010"
down_revision = "20260404_009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns
    op.add_column("achievement_definitions", sa.Column("hint", sa.Text(), nullable=True))
    op.add_column("achievement_definitions", sa.Column("is_secret", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("achievement_definitions", sa.Column("is_anti", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("achievement_definitions", sa.Column("recommendation", sa.Text(), nullable=True))

    # Update category constraint for 8 categories
    op.drop_constraint("ck_achdef_category", "achievement_definitions")
    op.create_check_constraint(
        "ck_achdef_category_v2", "achievement_definitions",
        "category IN ('results','skills','challenges','progression','arena','social','narrative','secret')",
    )

    # Add indexes
    op.create_index("idx_achievement_definitions_category", "achievement_definitions", ["category"])
    op.create_index("idx_achievement_definitions_rarity", "achievement_definitions", ["rarity"])


def downgrade() -> None:
    op.drop_index("idx_achievement_definitions_rarity", table_name="achievement_definitions")
    op.drop_index("idx_achievement_definitions_category", table_name="achievement_definitions")
    op.drop_constraint("ck_achdef_category_v2", "achievement_definitions")
    op.create_check_constraint(
        "ck_achdef_category", "achievement_definitions",
        "category IN ('results','skills','challenges','progression')",
    )
    op.drop_column("achievement_definitions", "recommendation")
    op.drop_column("achievement_definitions", "is_anti")
    op.drop_column("achievement_definitions", "is_secret")
    op.drop_column("achievement_definitions", "hint")
