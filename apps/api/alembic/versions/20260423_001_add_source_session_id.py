"""Add source_session_id to training_sessions (retrain-from-session lineage).

Revision ID: 20260423_001
Revises: 20260421_003
Create Date: 2026-04-23

Zone 4 — retrain flow: when user clicks «Повторить сценарий» on /results,
the new session is created as a clone of the previous one. We record the
lineage via `source_session_id` (FK to training_sessions.id, ON DELETE SET
NULL) so analytics can see «which sessions were retrains of which
originals» and so the UI can surface a subtle "this is a retrain" badge.

Nullable + optional: existing sessions and new non-retrain sessions both
have NULL. Fully backward-compatible — removing this column only erases
retrain provenance, nothing else depends on it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "20260423_001"
down_revision: Union[str, Sequence[str], None] = "20260421_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent check — safe to replay in dev if already applied manually.
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'training_sessions' "
            "AND column_name = 'source_session_id'"
        )
    ).fetchone()
    if exists:
        return

    op.add_column(
        "training_sessions",
        sa.Column(
            "source_session_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_training_sessions_source_session_id",
        "training_sessions",
        "training_sessions",
        ["source_session_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_training_sessions_source_session_id",
        "training_sessions",
        ["source_session_id"],
        unique=False,
    )


def downgrade() -> None:
    # Safe: retrain lineage is pure metadata, nothing else reads it. Drop
    # index first, then FK, then column — standard Alembic cleanup order.
    op.drop_index(
        "ix_training_sessions_source_session_id",
        table_name="training_sessions",
    )
    op.drop_constraint(
        "fk_training_sessions_source_session_id",
        "training_sessions",
        type_="foreignkey",
    )
    op.drop_column("training_sessions", "source_session_id")
