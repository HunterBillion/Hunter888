"""Команда v2 — per-manager KPI targets.

Revision ID: 20260501_002
Revises: 20260501_001
Create Date: 2026-05-01

Background
----------

The Команда (Team) panel surfaces three real KPIs per manager via
`GET /team/analytics`: sessions count last 30 days, average score last
30 days, and days since last session. PR #122 (Команда v2) shipped the
read side. This PR adds the *targets* side — a ROP can set per-manager
goals, the panel shows actual vs target, and the FE flags red when the
manager is below.

Schema
------

One small table keyed on user_id (1:1 with users.id, FK CASCADE so
deleted users drop their targets cleanly). Three nullable columns —
nullable so a brand-new manager has no targets until ROP sets one,
and "no target" means "don't show progress bar" in the FE rather than
"target is zero".

Re-runnability
--------------

Idempotent — uses `IF NOT EXISTS` via inspector check. Downgrade drops
the whole table; no data loss for the rest of the schema.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260501_002"
down_revision: Union[str, Sequence[str], None] = "20260501_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_name = :name "
                "LIMIT 1"
            ),
            {"name": name},
        ).scalar()
        is not None
    )


def upgrade() -> None:
    if not _table_exists("manager_kpi_targets"):
        op.create_table(
            "manager_kpi_targets",
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            # Nullable on purpose — "no target" ≠ "target=0".
            sa.Column("target_sessions_per_month", sa.Integer(), nullable=True),
            sa.Column("target_avg_score", sa.Float(), nullable=True),
            sa.Column("target_max_days_without_session", sa.Integer(), nullable=True),
            sa.Column(
                "updated_by",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "target_sessions_per_month IS NULL OR target_sessions_per_month >= 0",
                name="ck_kpi_target_sessions_nonneg",
            ),
            sa.CheckConstraint(
                "target_avg_score IS NULL OR (target_avg_score >= 0 AND target_avg_score <= 100)",
                name="ck_kpi_target_score_in_range",
            ),
            sa.CheckConstraint(
                "target_max_days_without_session IS NULL OR target_max_days_without_session >= 0",
                name="ck_kpi_target_days_nonneg",
            ),
        )


def downgrade() -> None:
    if _table_exists("manager_kpi_targets"):
        op.drop_table("manager_kpi_targets")
