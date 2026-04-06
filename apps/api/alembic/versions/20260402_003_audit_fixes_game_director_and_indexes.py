"""Add Game Director fields to client_stories + FK indexes across 6 models.

Part of the deep audit fix batch:
- 6 new columns on client_stories for Game Director lifecycle (relationship_score,
  lifecycle_state, active_storylets, consequence_log, memory, total_calls)
- 18 missing FK indexes across training_sessions, assigned_trainings, user_achievements,
  leaderboard_snapshots, checkpoints, script_embeddings, tournament_entries,
  tournament_participants, quiz_participants, user_consents

Revision ID: 20260402_003
Revises: 20260402_002
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers
revision: str = "20260402_003"
down_revision: Union[str, None] = "20260402_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ══════════════════════════════════════════════════════════════════════
    # 1. New columns on client_stories (Game Director lifecycle)
    # ══════════════════════════════════════════════════════════════════════
    op.add_column(
        "client_stories",
        sa.Column("relationship_score", sa.Float(), nullable=True, server_default="50.0"),
    )
    op.add_column(
        "client_stories",
        sa.Column("lifecycle_state", sa.String(50), nullable=True, server_default="'FIRST_CONTACT'"),
    )
    op.add_column(
        "client_stories",
        sa.Column(
            "active_storylets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "client_stories",
        sa.Column(
            "consequence_log",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "client_stories",
        sa.Column(
            "memory",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "client_stories",
        sa.Column("total_calls", sa.Integer(), nullable=True, server_default="0"),
    )

    # ══════════════════════════════════════════════════════════════════════
    # 2. Missing FK indexes (performance: prevents full table scans)
    # ══════════════════════════════════════════════════════════════════════

    # -- training_sessions --
    op.create_index(
        "ix_training_sessions_user_id",
        "training_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_training_sessions_scenario_id",
        "training_sessions",
        ["scenario_id"],
    )

    # -- assigned_trainings --
    op.create_index(
        "ix_assigned_trainings_user_id",
        "assigned_trainings",
        ["user_id"],
    )
    op.create_index(
        "ix_assigned_trainings_scenario_id",
        "assigned_trainings",
        ["scenario_id"],
    )
    op.create_index(
        "ix_assigned_trainings_assigned_by",
        "assigned_trainings",
        ["assigned_by"],
    )

    # -- user_achievements --
    op.create_index(
        "ix_user_achievements_user_id",
        "user_achievements",
        ["user_id"],
    )
    op.create_index(
        "ix_user_achievements_achievement_id",
        "user_achievements",
        ["achievement_id"],
    )

    # -- leaderboard_snapshots --
    op.create_index(
        "ix_leaderboard_snapshots_user_id",
        "leaderboard_snapshots",
        ["user_id"],
    )

    # -- checkpoints --
    op.create_index(
        "ix_checkpoints_script_id",
        "checkpoints",
        ["script_id"],
    )

    # -- script_embeddings --
    op.create_index(
        "ix_script_embeddings_checkpoint_id",
        "script_embeddings",
        ["checkpoint_id"],
    )

    # -- tournament_entries --
    op.create_index(
        "ix_tournament_entries_tournament_id",
        "tournament_entries",
        ["tournament_id"],
    )
    op.create_index(
        "ix_tournament_entries_user_id",
        "tournament_entries",
        ["user_id"],
    )
    op.create_index(
        "ix_tournament_entries_session_id",
        "tournament_entries",
        ["session_id"],
    )

    # -- tournament_participants --
    # Note: ix_tp_tournament_user composite (tournament_id, user_id) already covers
    # tournament_id lookups via leftmost prefix, so only user_id needs a standalone index.
    op.create_index(
        "ix_tournament_participants_user_id",
        "tournament_participants",
        ["user_id"],
    )

    # -- quiz_participants --
    op.create_index(
        "ix_quiz_participants_user_id",
        "quiz_participants",
        ["user_id"],
    )

    # -- user_consents --
    op.create_index(
        "ix_user_consents_user_id",
        "user_consents",
        ["user_id"],
    )


def downgrade() -> None:
    # ══════════════════════════════════════════════════════════════════════
    # Drop indexes (reverse order)
    # ══════════════════════════════════════════════════════════════════════
    op.drop_index("ix_user_consents_user_id", table_name="user_consents")
    op.drop_index("ix_quiz_participants_user_id", table_name="quiz_participants")
    op.drop_index("ix_tournament_participants_user_id", table_name="tournament_participants")
    op.drop_index("ix_tournament_entries_session_id", table_name="tournament_entries")
    op.drop_index("ix_tournament_entries_user_id", table_name="tournament_entries")
    op.drop_index("ix_tournament_entries_tournament_id", table_name="tournament_entries")
    op.drop_index("ix_script_embeddings_checkpoint_id", table_name="script_embeddings")
    op.drop_index("ix_checkpoints_script_id", table_name="checkpoints")
    op.drop_index("ix_leaderboard_snapshots_user_id", table_name="leaderboard_snapshots")
    op.drop_index("ix_user_achievements_achievement_id", table_name="user_achievements")
    op.drop_index("ix_user_achievements_user_id", table_name="user_achievements")
    op.drop_index("ix_assigned_trainings_assigned_by", table_name="assigned_trainings")
    op.drop_index("ix_assigned_trainings_scenario_id", table_name="assigned_trainings")
    op.drop_index("ix_assigned_trainings_user_id", table_name="assigned_trainings")
    op.drop_index("ix_training_sessions_scenario_id", table_name="training_sessions")
    op.drop_index("ix_training_sessions_user_id", table_name="training_sessions")

    # ══════════════════════════════════════════════════════════════════════
    # Drop columns (reverse order)
    # ══════════════════════════════════════════════════════════════════════
    op.drop_column("client_stories", "total_calls")
    op.drop_column("client_stories", "memory")
    op.drop_column("client_stories", "consequence_log")
    op.drop_column("client_stories", "active_storylets")
    op.drop_column("client_stories", "lifecycle_state")
    op.drop_column("client_stories", "relationship_score")
