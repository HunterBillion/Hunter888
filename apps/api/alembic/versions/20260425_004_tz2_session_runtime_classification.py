"""TZ-2 §6.2/6.3 — canonical Session runtime classification.

Revision ID: 20260425_004
Revises: 20260425_003
Create Date: 2026-04-25

Adds two nullable columns to ``training_sessions``:
  * ``mode``         §6.2 — chat | call | center
  * ``runtime_type`` §6.3 — training_simulation | training_real_case |
                            crm_call | crm_chat | center_single_call

Both are NULL for legacy rows (cannot be derived without runtime
context); new rows are populated by ``api/training.start_session`` and
``services/runtime_finalizer`` (Phase 1). CHECK constraints enforce
the catalog at DB level, NOT VALID-then-VALIDATE pattern so existing
NULL rows don't block the upgrade.

Down migration drops the columns.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260425_004"
down_revision: Union[str, Sequence[str], None] = "20260425_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_MODES = ("chat", "call", "center")
_RUNTIME_TYPES = (
    "training_simulation", "training_real_case",
    "crm_call", "crm_chat", "center_single_call",
)


def _quoted(values: Sequence[str]) -> str:
    return ",".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.add_column(
        "training_sessions",
        sa.Column("mode", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "training_sessions",
        sa.Column("runtime_type", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_training_sessions_mode",
        "training_sessions",
        ["mode"],
    )
    op.create_index(
        "ix_training_sessions_runtime_type",
        "training_sessions",
        ["runtime_type"],
    )

    # CHECK with IS NULL escape clause so legacy rows (which stay NULL)
    # don't break VALIDATE.
    op.execute(
        f"ALTER TABLE training_sessions ADD CONSTRAINT ck_training_sessions_mode "
        f"CHECK (mode IS NULL OR mode IN ({_quoted(_MODES)})) NOT VALID"
    )
    op.execute(
        f"ALTER TABLE training_sessions ADD CONSTRAINT ck_training_sessions_runtime_type "
        f"CHECK (runtime_type IS NULL OR runtime_type IN ({_quoted(_RUNTIME_TYPES)})) NOT VALID"
    )
    op.execute("ALTER TABLE training_sessions VALIDATE CONSTRAINT ck_training_sessions_mode")
    op.execute("ALTER TABLE training_sessions VALIDATE CONSTRAINT ck_training_sessions_runtime_type")


def downgrade() -> None:
    op.execute("ALTER TABLE training_sessions DROP CONSTRAINT IF EXISTS ck_training_sessions_runtime_type")
    op.execute("ALTER TABLE training_sessions DROP CONSTRAINT IF EXISTS ck_training_sessions_mode")
    op.drop_index("ix_training_sessions_runtime_type", table_name="training_sessions")
    op.drop_index("ix_training_sessions_mode", table_name="training_sessions")
    op.drop_column("training_sessions", "runtime_type")
    op.drop_column("training_sessions", "mode")
