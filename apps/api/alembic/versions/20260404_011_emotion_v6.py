"""Emotion system v6: intensity, compound emotions, graph variants (DOC_08).

Revision ID: 20260404_011
Revises: 20260404_010
Create Date: 2026-04-04

Adds graph_variant to archetype_emotion_configs.
Adds intensity/compound/micro columns to emotion_session_log.
All nullable for backward compatibility.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260404_011"
down_revision = "20260404_010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # archetype_emotion_configs: graph variant per archetype
    op.add_column("archetype_emotion_configs", sa.Column(
        "graph_variant", sa.String(20), nullable=True, server_default="'standard'",
    ))

    # emotion_session_log: extended per-turn data
    op.add_column("emotion_session_log", sa.Column("intensity_level", sa.String(10), nullable=True))
    op.add_column("emotion_session_log", sa.Column("intensity_value", sa.Float(), nullable=True))
    op.add_column("emotion_session_log", sa.Column("compound_emotion", sa.String(30), nullable=True))
    op.add_column("emotion_session_log", sa.Column("micro_expression", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("emotion_session_log", "micro_expression")
    op.drop_column("emotion_session_log", "compound_emotion")
    op.drop_column("emotion_session_log", "intensity_value")
    op.drop_column("emotion_session_log", "intensity_level")
    op.drop_column("archetype_emotion_configs", "graph_variant")
