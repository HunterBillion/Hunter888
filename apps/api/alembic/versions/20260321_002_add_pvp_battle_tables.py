"""Add PvP Battle tables (Agent 8)

Revision ID: 20260321_002
Revises: fead4bf27c54
Create Date: 2026-03-21 12:00:00.000000

Tables:
- pvp_seasons: seasonal competitive periods
- pvp_ratings: Glicko-2 rating per user
- pvp_duels: individual PvP duel records
- pvp_match_queue: matchmaking queue entries
- pvp_anti_cheat_logs: anti-cheat detection log
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20260321_002'
down_revision: Union[str, None] = 'fead4bf27c54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Enum types for column references ──
# create_type=False on postgresql.ENUM prevents auto-CREATE TYPE during
# op.create_table(). We create them manually via raw SQL with exception
# handling so the migration is idempotent (survives partial runs).
duel_status_enum = postgresql.ENUM(
    'pending', 'round_1', 'swap', 'round_2', 'judging',
    'completed', 'cancelled', 'disputed',
    name='duelstatus',
    create_type=False,
)
match_queue_status_enum = postgresql.ENUM(
    'waiting', 'matched', 'expired', 'cancelled',
    name='matchqueuestatus',
    create_type=False,
)
anti_cheat_check_type_enum = postgresql.ENUM(
    'statistical', 'behavioral', 'ai_detector', 'latency', 'semantic',
    name='anticheatchecktype',
    create_type=False,
)
anti_cheat_action_enum = postgresql.ENUM(
    'none', 'flag_review', 'temp_ban_24h', 'rating_freeze',
    'rating_penalty', 'disqualification',
    name='anticheataction',
    create_type=False,
)
pvp_rank_tier_enum = postgresql.ENUM(
    'bronze', 'silver', 'gold', 'platinum', 'diamond', 'unranked',
    name='pvpranktier',
    create_type=False,
)
duel_difficulty_enum = postgresql.ENUM(
    'easy', 'medium', 'hard',
    name='dueldifficulty',
    create_type=False,
)


def _create_enum_idempotent(name: str, values: list[str]) -> None:
    """Create a PostgreSQL enum type, ignoring if it already exists."""
    vals = ", ".join(f"'{v}'" for v in values)
    op.execute(sa.text(
        f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({vals}); "
        f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    ))


def upgrade() -> None:
    # Create enum types idempotently (safe for partial re-runs)
    _create_enum_idempotent('duelstatus', [
        'pending', 'round_1', 'swap', 'round_2', 'judging',
        'completed', 'cancelled', 'disputed',
    ])
    _create_enum_idempotent('matchqueuestatus', [
        'waiting', 'matched', 'expired', 'cancelled',
    ])
    _create_enum_idempotent('anticheatchecktype', [
        'statistical', 'behavioral', 'ai_detector', 'latency', 'semantic',
    ])
    _create_enum_idempotent('anticheataction', [
        'none', 'flag_review', 'temp_ban_24h', 'rating_freeze',
        'rating_penalty', 'disqualification',
    ])
    _create_enum_idempotent('pvpranktier', [
        'bronze', 'silver', 'gold', 'platinum', 'diamond', 'unranked',
    ])
    _create_enum_idempotent('dueldifficulty', ['easy', 'medium', 'hard'])

    # pvp_seasons (create first — referenced by pvp_ratings)
    op.create_table(
        'pvp_seasons',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
        sa.Column('rewards', postgresql.JSONB()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # pvp_ratings
    op.create_table(
        'pvp_ratings',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=False, server_default=sa.text('1500.0')),
        sa.Column('rd', sa.Float(), nullable=False, server_default=sa.text('350.0')),
        sa.Column('volatility', sa.Float(), nullable=False, server_default=sa.text('0.06')),
        sa.Column('rank_tier', pvp_rank_tier_enum, nullable=False, server_default=sa.text("'unranked'")),
        sa.Column('wins', sa.Integer(), server_default=sa.text('0')),
        sa.Column('losses', sa.Integer(), server_default=sa.text('0')),
        sa.Column('draws', sa.Integer(), server_default=sa.text('0')),
        sa.Column('total_duels', sa.Integer(), server_default=sa.text('0')),
        sa.Column('placement_done', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('placement_count', sa.Integer(), server_default=sa.text('0')),
        sa.Column('peak_rating', sa.Float(), server_default=sa.text('1500.0')),
        sa.Column('peak_tier', pvp_rank_tier_enum, nullable=False, server_default=sa.text("'unranked'")),
        sa.Column('current_streak', sa.Integer(), server_default=sa.text('0')),
        sa.Column('best_streak', sa.Integer(), server_default=sa.text('0')),
        sa.Column('season_id', sa.UUID(), nullable=True),
        sa.Column('last_played', sa.DateTime(timezone=True)),
        sa.Column('last_rd_decay', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['season_id'], ['pvp_seasons.id']),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('ix_pvp_ratings_user_id', 'pvp_ratings', ['user_id'])
    op.create_index('ix_pvp_ratings_rating', 'pvp_ratings', ['rating'])

    # pvp_duels
    op.create_table(
        'pvp_duels',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('player1_id', sa.UUID(), nullable=False),
        sa.Column('player2_id', sa.UUID(), nullable=False),
        sa.Column('scenario_id', sa.UUID(), nullable=True),
        sa.Column('status', duel_status_enum, nullable=False, server_default=sa.text("'pending'")),
        sa.Column('difficulty', duel_difficulty_enum, nullable=False, server_default=sa.text("'medium'")),
        sa.Column('round_1_data', postgresql.JSONB()),
        sa.Column('round_2_data', postgresql.JSONB()),
        sa.Column('player1_total', sa.Float(), server_default=sa.text('0.0')),
        sa.Column('player2_total', sa.Float(), server_default=sa.text('0.0')),
        sa.Column('winner_id', sa.UUID()),
        sa.Column('is_draw', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('duration_seconds', sa.Integer(), server_default=sa.text('0')),
        sa.Column('round_number', sa.Integer(), server_default=sa.text('1')),
        sa.Column('anti_cheat_flags', postgresql.JSONB()),
        sa.Column('replay_url', sa.String(500)),
        sa.Column('is_pve', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('rating_change_applied', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('player1_rating_delta', sa.Float(), server_default=sa.text('0.0')),
        sa.Column('player2_rating_delta', sa.Float(), server_default=sa.text('0.0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['player1_id'], ['users.id']),
        sa.ForeignKeyConstraint(['player2_id'], ['users.id']),
        sa.ForeignKeyConstraint(['scenario_id'], ['scenarios.id']),
    )
    op.create_index('ix_pvp_duels_player1_id', 'pvp_duels', ['player1_id'])
    op.create_index('ix_pvp_duels_player2_id', 'pvp_duels', ['player2_id'])
    op.create_index('ix_pvp_duels_status', 'pvp_duels', ['status'])

    # pvp_match_queue
    op.create_table(
        'pvp_match_queue',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=False),
        sa.Column('rd', sa.Float(), nullable=False),
        sa.Column('queued_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('status', match_queue_status_enum, nullable=False, server_default=sa.text("'waiting'")),
        sa.Column('expanded_range', sa.Float(), server_default=sa.text('0.0')),
        sa.Column('matched_with', sa.UUID()),
        sa.Column('duel_id', sa.UUID()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_index('ix_pvp_match_queue_user_id', 'pvp_match_queue', ['user_id'])

    # pvp_anti_cheat_logs
    op.create_table(
        'pvp_anti_cheat_logs',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('duel_id', sa.UUID()),
        sa.Column('check_type', anti_cheat_check_type_enum, nullable=False),
        sa.Column('score', sa.Float(), nullable=False, server_default=sa.text('0.0')),
        sa.Column('flagged', sa.Boolean(), server_default=sa.text('false')),
        sa.Column('action_taken', anti_cheat_action_enum, nullable=False, server_default=sa.text("'none'")),
        sa.Column('details', postgresql.JSONB()),
        sa.Column('resolved_by', sa.UUID()),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
        sa.Column('resolution', sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['duel_id'], ['pvp_duels.id']),
    )
    op.create_index('ix_pvp_anti_cheat_logs_user_id', 'pvp_anti_cheat_logs', ['user_id'])
    op.create_index('ix_pvp_anti_cheat_logs_duel_id', 'pvp_anti_cheat_logs', ['duel_id'])


def downgrade() -> None:
    op.drop_table('pvp_anti_cheat_logs')
    op.drop_table('pvp_match_queue')
    op.drop_table('pvp_duels')
    op.drop_table('pvp_ratings')
    op.drop_table('pvp_seasons')

    # Drop enums
    op.execute(sa.text("DROP TYPE IF EXISTS dueldifficulty"))
    op.execute(sa.text("DROP TYPE IF EXISTS pvpranktier"))
    op.execute(sa.text("DROP TYPE IF EXISTS anticheataction"))
    op.execute(sa.text("DROP TYPE IF EXISTS anticheatchecktype"))
    op.execute(sa.text("DROP TYPE IF EXISTS matchqueuestatus"))
    op.execute(sa.text("DROP TYPE IF EXISTS duelstatus"))
