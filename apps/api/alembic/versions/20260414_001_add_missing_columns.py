"""Add missing ORM columns: training_sessions.real_client_id, scenarios.template_id.

These columns exist in ORM models but were never migrated.
Discovered during 9-layer diagnostic: all 500s on /api/dashboard,
/api/scenarios, /api/training/history were caused by this mismatch.

Revision ID: 20260414_001
Revises: 20260412_002
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260414_001"
down_revision: Union[str, None] = "20260412_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c)"
    ), {"t": table, "c": column})
    return result.scalar()


def upgrade() -> None:
    if not _col_exists("training_sessions", "real_client_id"):
        op.add_column("training_sessions", sa.Column(
            "real_client_id", UUID(as_uuid=True),
            sa.ForeignKey("real_clients.id", ondelete="SET NULL"),
            nullable=True,
        ))
        op.create_index("ix_training_sessions_real_client_id", "training_sessions", ["real_client_id"])

    if not _col_exists("scenarios", "template_id"):
        op.add_column("scenarios", sa.Column(
            "template_id", UUID(as_uuid=True),
            sa.ForeignKey("scenario_templates.id", ondelete="SET NULL"),
            nullable=True,
        ))
        op.create_index("ix_scenarios_template_id", "scenarios", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_scenarios_template_id", table_name="scenarios")
    op.drop_column("scenarios", "template_id")
    op.drop_index("ix_training_sessions_real_client_id", table_name="training_sessions")
    op.drop_column("training_sessions", "real_client_id")
