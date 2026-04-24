"""Phase 1 — ConversationCompletionPolicy terminal contract columns.

Revision ID: 20260424_004
Revises: 20260424_003
Create Date: 2026-04-24

Additive only — new nullable columns on ``training_sessions`` and
``pvp_duels``. No existing data touched. Rollout safe on prod: the
columns stay NULL for historical sessions and get populated once
``ConversationCompletionPolicy.finalize_*`` wires into the producers.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260424_004"
down_revision: Union[str, Sequence[str], None] = "20260424_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _column_exists(table_name: str, column_name: str) -> bool:
    insp = _inspector()
    if not insp.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in insp.get_columns(table_name))


def upgrade() -> None:
    if not _column_exists("training_sessions", "terminal_outcome"):
        op.add_column(
            "training_sessions",
            sa.Column("terminal_outcome", sa.String(length=32), nullable=True),
        )
    if not _column_exists("training_sessions", "terminal_reason"):
        op.add_column(
            "training_sessions",
            sa.Column("terminal_reason", sa.String(length=32), nullable=True),
        )
    if not _column_exists("training_sessions", "completed_via"):
        op.add_column(
            "training_sessions",
            sa.Column("completed_via", sa.String(length=16), nullable=True),
        )

    if not _column_exists("pvp_duels", "terminal_outcome"):
        op.add_column(
            "pvp_duels",
            sa.Column("terminal_outcome", sa.String(length=32), nullable=True),
        )
    if not _column_exists("pvp_duels", "terminal_reason"):
        op.add_column(
            "pvp_duels",
            sa.Column("terminal_reason", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    for table_name, column in (
        ("pvp_duels", "terminal_reason"),
        ("pvp_duels", "terminal_outcome"),
        ("training_sessions", "completed_via"),
        ("training_sessions", "terminal_reason"),
        ("training_sessions", "terminal_outcome"),
    ):
        if _column_exists(table_name, column):
            op.drop_column(table_name, column)
