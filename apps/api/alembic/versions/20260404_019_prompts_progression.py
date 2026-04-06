"""Prompt registry + progression v2 tables (DOC_15 + DOC_16).

Revision ID: 20260404_019
Revises: 20260404_018
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260404_019"
down_revision = "20260404_018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DOC_16: Prompt versions table (data-driven prompt management)
    op.create_table(
        "prompt_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("prompt_type", sa.String(30), nullable=False),     # archetype|scenario|emotion|judge|personality|bot|template
        sa.Column("prompt_key", sa.String(80), nullable=False),      # skeptic|cold_modifier|cold_low|...
        sa.Column("version", sa.String(20), nullable=False, server_default="'v2'"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metrics", JSONB(), nullable=True),                 # A/B test results
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("prompt_type", "prompt_key", "version", name="uq_prompt_version"),
    )
    op.create_index("ix_prompt_versions_type_key", "prompt_versions", ["prompt_type", "prompt_key"])
    op.create_index("ix_prompt_versions_active", "prompt_versions", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_prompt_versions_active", table_name="prompt_versions")
    op.drop_index("ix_prompt_versions_type_key", table_name="prompt_versions")
    op.drop_table("prompt_versions")
