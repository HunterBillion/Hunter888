"""Phase 3 — PersonaSnapshot (Roadmap §8.1).

Revision ID: 20260425_001
Revises: 20260424_004
Create Date: 2026-04-25

New ``persona_snapshots`` table — insert-only, immutable copy of the
identity/voice/persona per training session. Replaces the ad-hoc
``_session_voices`` in-memory dict and the drifting
``ClientProfile``/``ClientStory``/``custom_params`` sources.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260425_001"
down_revision: Union[str, Sequence[str], None] = "20260424_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return _inspector().has_table(name)


def _index_exists(table: str, name: str) -> bool:
    if not _table_exists(table):
        return False
    return any(idx["name"] == name for idx in _inspector().get_indexes(table))


def upgrade() -> None:
    if not _table_exists("persona_snapshots"):
        op.create_table(
            "persona_snapshots",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column(
                "session_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("training_sessions.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "lead_client_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("lead_clients.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "client_story_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("client_stories.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("full_name", sa.String(length=200), nullable=False),
            sa.Column("gender", sa.String(length=10), nullable=False),
            sa.Column("city", sa.String(length=100), nullable=True),
            sa.Column("age", sa.Integer(), nullable=True),
            sa.Column("archetype_code", sa.String(length=50), nullable=False),
            sa.Column("persona_label", sa.String(length=200), nullable=False),
            sa.Column("voice_id", sa.String(length=100), nullable=False),
            sa.Column("voice_provider", sa.String(length=30), nullable=False),
            sa.Column("voice_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("frozen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("source_ref", sa.String(length=60), nullable=False),
            sa.UniqueConstraint("session_id", name="uq_persona_snapshot_session_id"),
        )

    for index_name, cols in (
        ("ix_persona_snapshots_session_id", ["session_id"]),
        ("ix_persona_snapshots_lead_client_id", ["lead_client_id"]),
        ("ix_persona_snapshots_client_story_id", ["client_story_id"]),
    ):
        if not _index_exists("persona_snapshots", index_name):
            op.create_index(index_name, "persona_snapshots", cols, unique=False)


def downgrade() -> None:
    for index_name in (
        "ix_persona_snapshots_client_story_id",
        "ix_persona_snapshots_lead_client_id",
        "ix_persona_snapshots_session_id",
    ):
        if _index_exists("persona_snapshots", index_name):
            op.drop_index(index_name, table_name="persona_snapshots")
    if _table_exists("persona_snapshots"):
        op.drop_table("persona_snapshots")
