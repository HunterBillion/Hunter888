"""Add scenario version snapshots.

Revision ID: 20260423_002
Revises: 20260423_001
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260423_002"
down_revision: Union[str, Sequence[str], None] = "20260423_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :table_name"
    ), {"table_name": table_name}).fetchone())


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    return bool(conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table_name AND column_name = :column_name"
    ), {"table_name": table_name, "column_name": column_name}).fetchone())


def upgrade() -> None:
    if not _table_exists("scenario_versions"):
        op.create_table(
            "scenario_versions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="published"),
            sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["template_id"], ["scenario_templates.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("template_id", "version_number", name="uq_scenario_versions_template_version"),
        )
        op.create_index("ix_scenario_versions_template_id", "scenario_versions", ["template_id"])
        op.create_index("ix_scenario_versions_created_by", "scenario_versions", ["created_by"])
        op.create_index("ix_scenario_versions_template_status", "scenario_versions", ["template_id", "status"])

    # Backfill immutable v1 snapshots for already published templates. Without
    # this, old templates would keep producing sessions with NULL
    # scenario_version_id until someone edits them in the constructor.
    op.execute(sa.text("""
        INSERT INTO scenario_versions (
            id,
            template_id,
            version_number,
            status,
            snapshot,
            created_by,
            published_at
        )
        SELECT
            (
                substr(md5(st.id::text || ':scenario_version:v1'), 1, 8) || '-' ||
                substr(md5(st.id::text || ':scenario_version:v1'), 9, 4) || '-' ||
                substr(md5(st.id::text || ':scenario_version:v1'), 13, 4) || '-' ||
                substr(md5(st.id::text || ':scenario_version:v1'), 17, 4) || '-' ||
                substr(md5(st.id::text || ':scenario_version:v1'), 21, 12)
            )::uuid,
            st.id,
            1,
            'published',
            jsonb_build_object(
                'code', st.code,
                'name', st.name,
                'description', st.description,
                'group_name', st.group_name,
                'who_calls', st.who_calls,
                'funnel_stage', st.funnel_stage,
                'prior_contact', st.prior_contact,
                'initial_emotion', st.initial_emotion,
                'initial_emotion_variants', st.initial_emotion_variants,
                'client_awareness', st.client_awareness,
                'client_motivation', st.client_motivation,
                'typical_duration_minutes', st.typical_duration_minutes,
                'max_duration_minutes', st.max_duration_minutes,
                'typical_reply_count_min', st.typical_reply_count_min,
                'typical_reply_count_max', st.typical_reply_count_max,
                'target_outcome', st.target_outcome,
                'difficulty', st.difficulty,
                'archetype_weights', st.archetype_weights,
                'lead_sources', st.lead_sources,
                'stages', st.stages,
                'recommended_chains', st.recommended_chains,
                'trap_pool_categories', st.trap_pool_categories,
                'traps_count_min', st.traps_count_min,
                'traps_count_max', st.traps_count_max,
                'cascades_count', st.cascades_count,
                'scoring_modifiers', st.scoring_modifiers,
                'awareness_prompt', st.awareness_prompt,
                'stage_skip_reactions', st.stage_skip_reactions,
                'client_prompt_template', st.client_prompt_template,
                'is_active', st.is_active
            ),
            NULL,
            COALESCE(st.updated_at, st.created_at, now())
        FROM scenario_templates st
        WHERE NOT EXISTS (
            SELECT 1
            FROM scenario_versions sv
            WHERE sv.template_id = st.id
              AND sv.version_number = 1
        )
    """))

    if not _column_exists("training_sessions", "scenario_version_id"):
        op.add_column(
            "training_sessions",
            sa.Column("scenario_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_training_sessions_scenario_version_id",
            "training_sessions",
            "scenario_versions",
            ["scenario_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            "ix_training_sessions_scenario_version_id",
            "training_sessions",
            ["scenario_version_id"],
        )


def downgrade() -> None:
    if _column_exists("training_sessions", "scenario_version_id"):
        op.drop_index("ix_training_sessions_scenario_version_id", table_name="training_sessions")
        op.drop_constraint("fk_training_sessions_scenario_version_id", "training_sessions", type_="foreignkey")
        op.drop_column("training_sessions", "scenario_version_id")

    if _table_exists("scenario_versions"):
        op.drop_index("ix_scenario_versions_template_status", table_name="scenario_versions")
        op.drop_index("ix_scenario_versions_created_by", table_name="scenario_versions")
        op.drop_index("ix_scenario_versions_template_id", table_name="scenario_versions")
        op.drop_table("scenario_versions")
