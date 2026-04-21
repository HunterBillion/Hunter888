"""Add missing ORM columns batch 2: traps, objection_chains, daily_challenge_entries.

21 columns that exist in ORM models but were never migrated.
Discovered during full ORM-vs-DB comparison.

Revision ID: 20260414_002
Revises: 20260414_001
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "20260414_002"
down_revision: Union[str, None] = "20260414_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c)"
    ), {"t": table, "c": column})
    return result.scalar()


def _add_safe(table: str, col: sa.Column) -> None:
    if not _col_exists(table, col.name):
        op.add_column(table, col)


def upgrade() -> None:
    _j = sa.text("'[]'::jsonb")

    # ── traps: 15 columns ──
    _add_safe("traps", sa.Column("subcategory", sa.String(50)))
    _add_safe("traps", sa.Column("detection_level", sa.String(30)))
    _add_safe("traps", sa.Column("client_phrase_variants", JSONB, server_default=_j))
    _add_safe("traps", sa.Column("wrong_response_patterns", JSONB, server_default=_j))
    _add_safe("traps", sa.Column("wrong_response_example", sa.Text))
    _add_safe("traps", sa.Column("correct_response_patterns", JSONB, server_default=_j))
    _add_safe("traps", sa.Column("explanation", sa.Text))
    _add_safe("traps", sa.Column("law_reference", sa.Text))
    _add_safe("traps", sa.Column("archetype_codes", JSONB, server_default=_j))
    _add_safe("traps", sa.Column("profession_codes", JSONB, server_default=_j))
    _add_safe("traps", sa.Column("emotion_states", JSONB, server_default=_j))
    _add_safe("traps", sa.Column("triggers_trap_id", UUID(as_uuid=True),
              sa.ForeignKey("traps.id")))
    _add_safe("traps", sa.Column("blocked_by_trap_id", UUID(as_uuid=True),
              sa.ForeignKey("traps.id")))
    _add_safe("traps", sa.Column("fell_emotion_trigger", sa.String(50)))
    _add_safe("traps", sa.Column("dodged_emotion_trigger", sa.String(50)))

    # ── objection_chains: 5 columns ──
    _add_safe("objection_chains", sa.Column("archetype_codes", JSONB, server_default=_j))
    _add_safe("objection_chains", sa.Column("scenario_types", JSONB, server_default=_j))
    _add_safe("objection_chains", sa.Column("step_bonus", sa.Integer, server_default="5"))
    _add_safe("objection_chains", sa.Column("full_chain_bonus", sa.Integer, server_default="20"))
    _add_safe("objection_chains", sa.Column("max_score", sa.Integer, server_default="50"))

    # ── daily_challenge_entries: 1 column ──
    _add_safe("daily_challenge_entries", sa.Column("rank", sa.Integer))


def downgrade() -> None:
    pass  # Forward-only migration
