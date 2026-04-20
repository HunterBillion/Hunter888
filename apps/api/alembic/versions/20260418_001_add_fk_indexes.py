"""add btree indexes on 32 foreign-key columns that lacked them

Revision ID: 20260418_001
Revises: 20260410_001
Create Date: 2026-04-18

Addresses FIND-009 from production-readiness audit (2026-04-18).

A `pg_constraint` scan showed 32 FK columns without indexes. PostgreSQL does
NOT auto-index foreign keys (only primary keys + unique constraints). At the
current data size (users=45, sessions=26) queries stay fast via seq-scans,
but CASCADE DELETE on parent rows and JOINs over these columns degrade to
O(N) as data grows.

Indexes are created with IF NOT EXISTS to make this migration idempotent and
safe to run against a DB where some indexes may have been added ad-hoc.

All indexes are btree (default) — these columns hold UUIDs or small ints that
btree handles optimally.

No data changes, no downtime. `CREATE INDEX` (non-concurrent) is fine on an
offline DB; if running against a live production DB later, change to
`CREATE INDEX CONCURRENTLY` manually (alembic wraps in a transaction by
default, which blocks concurrent).
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260418_001"
down_revision = "20260410_001"
branch_labels = None
depends_on = None


# (table, column) pairs — source: pg_constraint scan 2026-04-18.
_FK_INDEXES: list[tuple[str, str]] = [
    ("api_logs", "session_id"),
    ("client_notifications", "client_id"),
    ("client_profiles", "chain_id"),
    ("client_profiles", "profession_id"),
    ("client_stories", "client_profile_id"),
    ("daily_challenge_entries", "session_id"),
    ("earned_achievements", "session_id"),
    ("episodic_memories", "session_id"),
    ("game_client_events", "session_id"),
    ("leaderboard_snapshots", "team_id"),
    ("manager_reminders", "client_id"),
    ("pve_boss_runs", "duel_id"),
    ("pvp_rapid_fire_matches", "player2_id"),
    ("pvp_ratings", "season_id"),
    ("pvp_teams", "duel_id"),
    ("pvp_teams", "player1_id"),
    ("pvp_teams", "player2_id"),
    ("reviews", "user_id"),
    ("story_stage_directions", "session_id"),
    ("team_challenges", "created_by"),
    ("team_challenges", "winner_team_id"),
    ("team_matches", "winner_team_id"),
    ("team_matches", "team_a_id"),
    ("team_matches", "team_b_id"),
    ("team_quiz_teams", "player2_id"),
    ("team_quiz_teams", "player1_id"),
    ("tournaments", "theme_id"),
    ("training_sessions", "custom_character_id"),
    ("traps", "blocked_by_trap_id"),
    ("traps", "triggers_trap_id"),
    ("weekly_league_membership", "group_id"),
    ("wiki_update_log", "triggered_by_session_id"),
]


def upgrade() -> None:
    for table, col in _FK_INDEXES:
        idx_name = f"ix_{table}_{col}"
        op.execute(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table}" ("{col}")')


def downgrade() -> None:
    for table, col in _FK_INDEXES:
        idx_name = f"ix_{table}_{col}"
        op.execute(f'DROP INDEX IF EXISTS "{idx_name}"')
