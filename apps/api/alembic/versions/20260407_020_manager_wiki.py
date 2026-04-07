"""Manager Wiki — Karpathy pattern knowledge base per manager.

Revision ID: 20260407_020
Revises: 20260404_019
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260407_020"
down_revision = "20260404_019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. manager_wikis — root wiki per manager
    op.create_table(
        "manager_wikis",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("manager_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("pages_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sessions_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("patterns_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_ingest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_daily_synthesis_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_weekly_synthesis_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_scheduled_update_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_manager_wikis_manager_id", "manager_wikis", ["manager_id"], unique=True)

    # 2. wiki_pages — individual wiki pages (markdown)
    op.create_table(
        "wiki_pages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("wiki_id", UUID(as_uuid=True), sa.ForeignKey("manager_wikis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_path", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_sessions", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("page_type", sa.String(30), nullable=False),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("wiki_id", "page_path", name="uq_wiki_pages_wiki_path"),
    )
    op.create_index("ix_wiki_pages_wiki_id", "wiki_pages", ["wiki_id"])
    op.create_index("ix_wiki_pages_wiki_id_page_path", "wiki_pages", ["wiki_id", "page_path"])

    # 3. wiki_update_log — audit trail
    op.create_table(
        "wiki_update_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("wiki_id", UUID(as_uuid=True), sa.ForeignKey("manager_wikis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("pages_modified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("patterns_discovered", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("triggered_by_session_id", UUID(as_uuid=True), sa.ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="'pending'"),
        sa.Column("error_msg", sa.Text(), nullable=True),
    )
    op.create_index("ix_wiki_update_log_wiki_id", "wiki_update_log", ["wiki_id"])
    op.create_index("ix_wiki_update_log_action_status", "wiki_update_log", ["action", "status"])

    # 4. manager_patterns — discovered behavioral patterns
    op.create_table(
        "manager_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("manager_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pattern_code", sa.String(100), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sessions_in_pattern", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impact_on_score_delta", sa.Float(), nullable=True),
        sa.Column("archetype_filter", sa.String(100), nullable=True),
        sa.Column("mitigation_technique", sa.Text(), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("manager_id", "pattern_code", name="uq_manager_patterns_code"),
    )
    op.create_index("ix_manager_patterns_manager_id", "manager_patterns", ["manager_id"])

    # 5. manager_techniques — effective techniques
    op.create_table(
        "manager_techniques",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("manager_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("technique_code", sa.String(100), nullable=False),
        sa.Column("technique_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("applicable_to_archetype", sa.String(100), nullable=True),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rate", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("how_to_apply", sa.Text(), nullable=True),
        sa.Column("exemplar_sessions", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_manager_techniques_manager_id", "manager_techniques", ["manager_id"])


def downgrade() -> None:
    op.drop_table("manager_techniques")
    op.drop_table("manager_patterns")
    op.drop_table("wiki_update_log")
    op.drop_table("wiki_pages")
    op.drop_table("manager_wikis")
