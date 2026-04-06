"""Add Behavioral Intelligence tables.

Creates:
- behavior_snapshots — per-session behavioral signals
- manager_emotion_profiles — aggregated OCEAN + confidence/stress/adaptability
- progress_trends — trend detection with alerts
- daily_advice — personalized daily recommendations

Revision ID: 20260324_003
Revises: 20260324_arena
Create Date: 2026-03-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260324_003"
down_revision: Union[str, None] = "20260324_arena"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Note: using String(20) instead of PostgreSQL ENUM types for direction/alert_severity
    # to avoid idempotency issues with CREATE TYPE in migration reruns.
    # Validation is handled at the ORM/application level via Python enums.

    # behavior_snapshots
    op.create_table(
        "behavior_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("session_type", sa.String(20), nullable=False),
        sa.Column("avg_response_time_ms", sa.Integer(), nullable=True),
        sa.Column("min_response_time_ms", sa.Integer(), nullable=True),
        sa.Column("max_response_time_ms", sa.Integer(), nullable=True),
        sa.Column("response_time_stddev", sa.Float(), nullable=True),
        sa.Column("avg_message_length", sa.Integer(), nullable=True),
        sa.Column("min_message_length", sa.Integer(), nullable=True),
        sa.Column("max_message_length", sa.Integer(), nullable=True),
        sa.Column("total_messages", sa.Integer(), server_default="0"),
        sa.Column("confidence_score", sa.Float(), server_default="50.0"),
        sa.Column("hesitation_count", sa.Integer(), server_default="0"),
        sa.Column("legal_term_density", sa.Float(), server_default="0.0"),
        sa.Column("stress_level", sa.Float(), server_default="30.0"),
        sa.Column("response_acceleration", sa.Float(), nullable=True),
        sa.Column("adaptability_score", sa.Float(), server_default="50.0"),
        sa.Column("emotion_response_quality", sa.Float(), nullable=True),
        sa.Column("signals", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_behavior_snapshots_user", "behavior_snapshots", ["user_id"])
    op.create_index("ix_behavior_snapshots_session", "behavior_snapshots", ["session_id"])

    # manager_emotion_profiles
    op.create_table(
        "manager_emotion_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("overall_confidence", sa.Float(), server_default="50.0"),
        sa.Column("overall_stress_resistance", sa.Float(), server_default="50.0"),
        sa.Column("overall_adaptability", sa.Float(), server_default="50.0"),
        sa.Column("overall_empathy", sa.Float(), server_default="50.0"),
        sa.Column("openness", sa.Float(), server_default="50.0"),
        sa.Column("conscientiousness", sa.Float(), server_default="50.0"),
        sa.Column("extraversion", sa.Float(), server_default="50.0"),
        sa.Column("agreeableness", sa.Float(), server_default="50.0"),
        sa.Column("neuroticism", sa.Float(), server_default="50.0"),
        sa.Column("performance_under_hostility", sa.Float(), nullable=True),
        sa.Column("performance_under_stress", sa.Float(), nullable=True),
        sa.Column("performance_with_empathy", sa.Float(), nullable=True),
        sa.Column("archetype_scores", JSONB, nullable=True),
        sa.Column("sessions_analyzed", sa.Integer(), server_default="0"),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # progress_trends
    op.create_table(
        "progress_trends",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_type", sa.String(10), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("score_delta", sa.Float(), server_default="0.0"),
        sa.Column("skill_trends", JSONB, nullable=True),
        sa.Column("confidence_trend", sa.String(20), nullable=True),
        sa.Column("stress_trend", sa.String(20), nullable=True),
        sa.Column("adaptability_trend", sa.String(20), nullable=True),
        sa.Column("alert_severity", sa.String(20), nullable=True),
        sa.Column("alert_message", sa.Text(), nullable=True),
        sa.Column("alert_seen_by_rop", sa.Boolean(), server_default="false"),
        sa.Column("sessions_count", sa.Integer(), server_default="0"),
        sa.Column("predicted_level_in_30d", sa.Integer(), nullable=True),
        sa.Column("predicted_score_in_7d", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_progress_trends_user", "progress_trends", ["user_id"])

    # daily_advice
    op.create_table(
        "daily_advice",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("advice_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="5"),
        sa.Column("action_type", sa.String(30), nullable=True),
        sa.Column("action_data", JSONB, nullable=True),
        sa.Column("source_analysis", JSONB, nullable=True),
        sa.Column("was_viewed", sa.Boolean(), server_default="false"),
        sa.Column("was_acted_on", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_daily_advice_user", "daily_advice", ["user_id"])
    op.create_index("ix_daily_advice_date", "daily_advice", ["advice_date"])


def downgrade() -> None:
    op.drop_table("daily_advice")
    op.drop_table("progress_trends")
    op.drop_table("manager_emotion_profiles")
    op.drop_table("behavior_snapshots")
