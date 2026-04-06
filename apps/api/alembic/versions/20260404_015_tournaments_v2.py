"""Tournament expansion: 4 types, BO3, themes, teams (DOC_12).

Revision ID: 20260404_015
Revises: 20260404_014
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "20260404_015"
down_revision = "20260404_014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend tournaments table
    op.add_column("tournaments", sa.Column("tournament_type", sa.String(30), server_default="weekly_sprint", nullable=False))
    op.add_column("tournaments", sa.Column("theme_id", UUID(as_uuid=True), nullable=True))
    op.add_column("tournaments", sa.Column("archetype_filter", JSONB(), nullable=True))
    op.add_column("tournaments", sa.Column("difficulty_filter", sa.String(20), nullable=True))
    op.create_index("ix_tournaments_type", "tournaments", ["tournament_type"])

    # BO3 for bracket matches
    op.add_column("bracket_matches", sa.Column("match_format", sa.String(10), server_default="bo1", nullable=False))
    op.add_column("bracket_matches", sa.Column("games", JSONB(), nullable=True))
    op.add_column("bracket_matches", sa.Column("games_won_p1", sa.Integer(), server_default="0", nullable=False))
    op.add_column("bracket_matches", sa.Column("games_won_p2", sa.Integer(), server_default="0", nullable=False))

    # Tournament themes
    op.create_table(
        "tournament_themes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("archetype_filter", JSONB(), nullable=False),
        sa.Column("difficulty_filter", sa.String(20), nullable=True),
        sa.Column("scenario_category", sa.String(50), nullable=True),
        sa.Column("icon_emoji", sa.String(10), nullable=False, server_default="''"),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Tournament teams
    op.create_table(
        "tournament_teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tournament_id", UUID(as_uuid=True), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_name", sa.String(50), nullable=False),
        sa.Column("captain_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_ids", JSONB(), nullable=False),
        sa.Column("team_rating", sa.Float(), server_default="1500.0"),
        sa.Column("motto", sa.String(200), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("wins", sa.Integer(), server_default="0"),
        sa.Column("losses", sa.Integer(), server_default="0"),
        sa.Column("draws", sa.Integer(), server_default="0"),
        sa.Column("points", sa.Integer(), server_default="0"),
        sa.Column("total_score", sa.Float(), server_default="0.0"),
        sa.Column("eliminated", sa.Boolean(), server_default="false"),
        sa.Column("final_placement", sa.Integer(), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_tournament_teams_tournament", "tournament_teams", ["tournament_id"])
    op.create_index("ix_tournament_teams_captain", "tournament_teams", ["captain_id"])

    # Team matches
    op.create_table(
        "team_matches",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tournament_id", UUID(as_uuid=True), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_num", sa.Integer(), nullable=False),
        sa.Column("match_index", sa.Integer(), nullable=False),
        sa.Column("team_a_id", UUID(as_uuid=True), sa.ForeignKey("tournament_teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_b_id", UUID(as_uuid=True), sa.ForeignKey("tournament_teams.id", ondelete="CASCADE"), nullable=True),
        sa.Column("team_a_score", sa.Float(), server_default="0.0"),
        sa.Column("team_b_score", sa.Float(), server_default="0.0"),
        sa.Column("winner_team_id", UUID(as_uuid=True), sa.ForeignKey("tournament_teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("individual_duels", JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(20), server_default="'pending'"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_team_matches_tournament", "team_matches", ["tournament_id"])
    op.create_index("ix_team_matches_round", "team_matches", ["tournament_id", "round_num", "match_index"])

    # FK for theme_id
    op.create_foreign_key("fk_tournaments_theme", "tournaments", "tournament_themes", ["theme_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_tournaments_theme", "tournaments", type_="foreignkey")
    op.drop_index("ix_team_matches_round", table_name="team_matches")
    op.drop_index("ix_team_matches_tournament", table_name="team_matches")
    op.drop_table("team_matches")
    op.drop_index("ix_tournament_teams_captain", table_name="tournament_teams")
    op.drop_index("ix_tournament_teams_tournament", table_name="tournament_teams")
    op.drop_table("tournament_teams")
    op.drop_table("tournament_themes")
    op.drop_column("bracket_matches", "games_won_p2")
    op.drop_column("bracket_matches", "games_won_p1")
    op.drop_column("bracket_matches", "games")
    op.drop_column("bracket_matches", "match_format")
    op.drop_index("ix_tournaments_type", table_name="tournaments")
    op.drop_column("tournaments", "difficulty_filter")
    op.drop_column("tournaments", "archetype_filter")
    op.drop_column("tournaments", "theme_id")
    op.drop_column("tournaments", "tournament_type")
