"""Create bracket tournament tables + add forfeit/scheduling fields.

Creates:
- tournament_participants: bracket tournament registration
- bracket_matches: single matches in bracket tournaments

Adds:
- Tournament.format, bracket_size, registration_end, current_round_num,
  bracket_data, round_deadline_hours columns
- BracketMatch includes forfeit_deadline, forfeit_by_id from the start

Revision ID: 20260402_002
Revises: 20260402_001
Create Date: 2026-04-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers
revision: str = "20260402_002"
down_revision: Union[str, None] = "20260402_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New columns on tournaments (bracket support) ───────────────────
    op.add_column("tournaments", sa.Column(
        "format", sa.String(20), server_default="leaderboard", nullable=False,
    ))
    op.add_column("tournaments", sa.Column(
        "bracket_size", sa.Integer(), nullable=True,
    ))
    op.add_column("tournaments", sa.Column(
        "registration_end", sa.DateTime(timezone=True), nullable=True,
    ))
    op.add_column("tournaments", sa.Column(
        "current_round_num", sa.Integer(), server_default="0", nullable=False,
    ))
    op.add_column("tournaments", sa.Column(
        "bracket_data", postgresql.JSONB(), nullable=True,
    ))
    op.add_column("tournaments", sa.Column(
        "round_deadline_hours", sa.Integer(), server_default="24", nullable=False,
    ))

    # ── tournament_participants ────────────────────────────────────────
    op.create_table(
        "tournament_participants",
        sa.Column("id", sa.UUID(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tournament_id", sa.UUID(),
                  sa.ForeignKey("tournaments.id"), nullable=False),
        sa.Column("user_id", sa.UUID(),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("rating_snapshot", sa.Float(), server_default="1500.0",
                  nullable=False),
        sa.Column("eliminated_at_round", sa.Integer(), nullable=True),
        sa.Column("final_placement", sa.Integer(), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_tp_tournament_user", "tournament_participants",
        ["tournament_id", "user_id"], unique=True,
    )

    # ── bracket_matches ────────────────────────────────────────────────
    op.create_table(
        "bracket_matches",
        sa.Column("id", sa.UUID(), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tournament_id", sa.UUID(),
                  sa.ForeignKey("tournaments.id"), nullable=False),
        sa.Column("round_num", sa.Integer(), nullable=False),
        sa.Column("match_index", sa.Integer(), nullable=False),
        sa.Column("player1_id", sa.UUID(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("player2_id", sa.UUID(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("winner_id", sa.UUID(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("duel_id", sa.UUID(),
                  sa.ForeignKey("pvp_duels.id"), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending",
                  nullable=False),
        sa.Column("player1_score", sa.Float(), nullable=True),
        sa.Column("player2_score", sa.Float(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forfeit_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("forfeit_by_id", sa.UUID(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_bm_tournament_round", "bracket_matches",
        ["tournament_id", "round_num", "match_index"],
    )
    op.create_index(
        "ix_bm_forfeit_deadline", "bracket_matches",
        ["tournament_id", "forfeit_deadline"],
    )


def downgrade() -> None:
    op.drop_index("ix_bm_forfeit_deadline", table_name="bracket_matches")
    op.drop_index("ix_bm_tournament_round", table_name="bracket_matches")
    op.drop_table("bracket_matches")
    op.drop_index("ix_tp_tournament_user", table_name="tournament_participants")
    op.drop_table("tournament_participants")
    op.drop_column("tournaments", "round_deadline_hours")
    op.drop_column("tournaments", "bracket_data")
    op.drop_column("tournaments", "current_round_num")
    op.drop_column("tournaments", "registration_end")
    op.drop_column("tournaments", "bracket_size")
    op.drop_column("tournaments", "format")
