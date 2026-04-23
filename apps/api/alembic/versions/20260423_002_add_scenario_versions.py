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

