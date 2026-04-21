"""S2-07c: Add composite indexes for training_sessions and team_analytics queries.

training_sessions(user_id, status, started_at) — covers the dominant query pattern:
    WHERE user_id IN (...) AND status = 'completed' AND started_at >= ?
    Used by: team_analytics (heatmap, weak_links, trends, ROI),
             weekly_report_generator (ranking, digest),
             weekly_report (session history).

training_sessions(started_at) — for date_trunc GROUP BY in team trends / daily activity.

Revision ID: 20260414_003
Revises: 20260414_002
"""
from alembic import op


revision: str = "20260414_003"
down_revision: str = "20260414_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index for the most common filter pattern:
    # WHERE user_id = ? AND status = 'completed' AND started_at >= ?
    op.create_index(
        "ix_training_sessions_user_status_started",
        "training_sessions",
        ["user_id", "status", "started_at"],
        if_not_exists=True,
    )
    # Standalone index for date_trunc GROUP BY (team trends, daily activity)
    op.create_index(
        "ix_training_sessions_started_at",
        "training_sessions",
        ["started_at"],
        if_not_exists=True,
    )
    # Weekly report lookup: user_id + week_start (already used in dedup check)
    op.create_index(
        "ix_weekly_reports_user_week",
        "weekly_reports",
        ["user_id", "week_start"],
        unique=True,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_weekly_reports_user_week", table_name="weekly_reports")
    op.drop_index("ix_training_sessions_started_at", table_name="training_sessions")
    op.drop_index("ix_training_sessions_user_status_started", table_name="training_sessions")
