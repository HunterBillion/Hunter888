"""Add constructor v2 columns to custom_characters.

Revision ID: 20260404_006
Revises: 20260402_005_phase3_fk_indexes_and_cascades
Create Date: 2026-04-04

DOC_02: Constructor expansion 4→8 steps.
Adds: context fields, emotion preset, environment modifiers, statistics, sharing.
All new fields are nullable for backward compatibility.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "20260404_006"
down_revision = "20260402_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 3: Client context
    op.add_column("custom_characters", sa.Column("family_preset", sa.String(30), nullable=True))
    op.add_column("custom_characters", sa.Column("creditors_preset", sa.String(20), nullable=True))
    op.add_column("custom_characters", sa.Column("debt_stage", sa.String(30), nullable=True))
    op.add_column("custom_characters", sa.Column("debt_range", sa.String(30), nullable=True))

    # Step 4: Emotional preset
    op.add_column("custom_characters", sa.Column("emotion_preset", sa.String(30), nullable=True))

    # Step 6: Environment modifiers
    op.add_column("custom_characters", sa.Column("bg_noise", sa.String(20), nullable=True))
    op.add_column("custom_characters", sa.Column("time_of_day", sa.String(20), nullable=True))
    op.add_column("custom_characters", sa.Column("client_fatigue", sa.String(20), nullable=True))

    # Step 7: Cached preview
    op.add_column("custom_characters", sa.Column("cached_dossier", sa.Text(), nullable=True))

    # Statistics
    op.add_column("custom_characters", sa.Column("play_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("custom_characters", sa.Column("best_score", sa.Integer(), nullable=True))
    op.add_column("custom_characters", sa.Column("avg_score", sa.Integer(), nullable=True))
    op.add_column("custom_characters", sa.Column("last_played_at", sa.DateTime(), nullable=True))

    # Metadata
    op.add_column("custom_characters", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("custom_characters", sa.Column("is_shared", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("custom_characters", sa.Column("share_code", sa.String(20), nullable=True))

    # Index for share_code lookups
    op.create_index("ix_custom_characters_share_code", "custom_characters", ["share_code"], unique=True)

    # Link training sessions to custom characters
    op.add_column("training_sessions", sa.Column("custom_character_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_training_sessions_custom_character_id",
        "training_sessions",
        "custom_characters",
        ["custom_character_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_training_sessions_custom_character_id", "training_sessions", type_="foreignkey")
    op.drop_column("training_sessions", "custom_character_id")

    op.drop_index("ix_custom_characters_share_code", table_name="custom_characters")
    op.drop_column("custom_characters", "share_code")
    op.drop_column("custom_characters", "is_shared")
    op.drop_column("custom_characters", "updated_at")
    op.drop_column("custom_characters", "last_played_at")
    op.drop_column("custom_characters", "avg_score")
    op.drop_column("custom_characters", "best_score")
    op.drop_column("custom_characters", "play_count")
    op.drop_column("custom_characters", "cached_dossier")
    op.drop_column("custom_characters", "client_fatigue")
    op.drop_column("custom_characters", "time_of_day")
    op.drop_column("custom_characters", "bg_noise")
    op.drop_column("custom_characters", "emotion_preset")
    op.drop_column("custom_characters", "debt_range")
    op.drop_column("custom_characters", "debt_stage")
    op.drop_column("custom_characters", "creditors_preset")
    op.drop_column("custom_characters", "family_preset")
