"""S3-01: Team challenge persistence — replace in-memory dict with PostgreSQL.

Creates:
  - team_challenges: challenge metadata (teams, type, status, deadline, bonus_xp)
  - team_challenge_progress: per-team score/completion tracking

Revision ID: 20260414_004
Revises: 20260414_003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "20260414_004"
down_revision = "20260414_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_challenges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("team_a_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_b_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("challenge_type", sa.String(30), nullable=False, server_default="score_avg"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active", index=True),
        sa.Column("scenario_code", sa.String(100), nullable=True),
        sa.Column("bonus_xp", sa.Integer, nullable=False, server_default="100"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("winner_team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_team_challenges_teams", "team_challenges", ["team_a_id", "team_b_id"])
    op.create_index("ix_team_challenges_status_deadline", "team_challenges", ["status", "deadline"])

    op.create_table(
        "team_challenge_progress",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("challenge_id", UUID(as_uuid=True), sa.ForeignKey("team_challenges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("completed_sessions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("total_members", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("challenge_id", "team_id", name="uq_challenge_team"),
    )
    op.create_index("ix_tcp_challenge_team", "team_challenge_progress", ["challenge_id", "team_id"])


def downgrade() -> None:
    op.drop_table("team_challenge_progress")
    op.drop_table("team_challenges")
