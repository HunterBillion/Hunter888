"""Add btree indexes on 20 FK columns missing indexes — FIND-006 audit fix

Revision ID: 20260421_001
Revises: 20260420_005
Create Date: 2026-04-21

Production audit (2026-04-21) found 20 FK columns without indexes. At current
data volume (users=10, sessions=few) queries fine via seq-scans, but under
real load (>10k users) JOINs and CASCADE DELETEs degrade to O(N).

All indexes are btree (default) — FK columns hold UUIDs or small ints that
btree handles optimally. IF NOT EXISTS + DO/EXCEPTION block handles tables
that may not exist on every deployment (seeded later or removed).

No data changes, no downtime. Forward-only migration.
"""
from __future__ import annotations

from alembic import op


revision = "20260421_001"
down_revision = "20260420_005"
branch_labels = None
depends_on = None


# (index_name, table, column) — 20 FK columns from production audit
_MISSING_FK_INDEXES = [
    ("ix_legal_document_parent_id", "legal_document", "parent_id"),
    ("ix_earned_achievements_session_id", "earned_achievements", "session_id"),
    ("ix_weekly_league_membership_group_id", "weekly_league_membership", "group_id"),
    ("ix_game_client_events_session_id", "game_client_events", "session_id"),
    ("ix_pvp_duels_winner_id", "pvp_duels", "winner_id"),
    ("ix_pvp_rapid_fire_matches_player2_id", "pvp_rapid_fire_matches", "player2_id"),
    ("ix_tournaments_theme_id", "tournaments", "theme_id"),
    ("ix_reviews_user_id", "reviews", "user_id"),
    ("ix_team_challenges_created_by", "team_challenges", "created_by"),
    ("ix_team_challenges_winner_team_id", "team_challenges", "winner_team_id"),
    ("ix_morning_drill_sessions_user_id", "morning_drill_sessions", "user_id"),
    ("ix_pvp_match_queue_matched_with", "pvp_match_queue", "matched_with"),
    ("ix_pvp_match_queue_duel_id", "pvp_match_queue", "duel_id"),
    ("ix_pvp_teams_player1_id", "pvp_teams", "player1_id"),
    ("ix_pvp_teams_player2_id", "pvp_teams", "player2_id"),
    ("ix_pvp_teams_duel_id", "pvp_teams", "duel_id"),
    ("ix_pve_boss_runs_duel_id", "pve_boss_runs", "duel_id"),
    ("ix_team_quiz_teams_player1_id", "team_quiz_teams", "player1_id"),
    ("ix_team_quiz_teams_player2_id", "team_quiz_teams", "player2_id"),
    ("ix_daily_challenge_entries_session_id", "daily_challenge_entries", "session_id"),
]


def upgrade() -> None:
    """Create 20 missing FK indexes, gracefully skip missing tables."""
    for idx_name, table, column in _MISSING_FK_INDEXES:
        op.execute(
            f"""
            DO $$ BEGIN
                CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ("{column}");
            EXCEPTION
                WHEN undefined_table THEN NULL;
                WHEN undefined_column THEN NULL;
            END $$;
            """
        )


def downgrade() -> None:
    """Drop the FK indexes created in upgrade."""
    for idx_name, _, _ in _MISSING_FK_INDEXES:
        op.execute(f'DROP INDEX IF EXISTS "{idx_name}"')
