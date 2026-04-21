"""Add gamification habit loop tables and columns.

New tables:
  - goal_completion_log (daily/weekly goal XP dedup)
  - streak_freezes (purchasable streak protection)
  - weekly_league_groups, weekly_league_membership (social pressure)
  - content_seasons, season_chapters (narrative structure)

New columns on manager_progress:
  - last_drill_date, drill_streak, best_drill_streak, total_drills
  - league_tier

Revision ID: 20260412_002
Revises: 20260412_001
Create Date: 2026-04-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '20260412_002'
down_revision: Union[str, None] = '20260412_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── goal_completion_log ──
    op.create_table(
        'goal_completion_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('goal_id', sa.String(50), nullable=False),
        sa.Column('period_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('xp_awarded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'goal_id', 'period_date', name='uq_goal_completion_user_goal_period'),
    )

    # ── streak_freezes ──
    op.create_table(
        'streak_freezes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('purchased_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('month_year', sa.String(7), nullable=False),
    )

    # ── weekly_league_groups ──
    op.create_table(
        'weekly_league_groups',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('week_start', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('league_tier', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('user_ids', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('standings', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('finalized', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('week_start', 'team_id', 'league_tier', name='uq_league_group_week_team_tier'),
    )

    # ── weekly_league_membership ──
    op.create_table(
        'weekly_league_membership',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('current_tier', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('weekly_league_groups.id', ondelete='SET NULL'), nullable=True),
        sa.Column('weekly_xp', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rank_in_group', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('promotion_history', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', name='uq_league_membership_user'),
    )

    # ── content_seasons ──
    op.create_table(
        'content_seasons',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('code', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('theme', sa.String(50), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('chapter_count', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('scenario_pool', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('special_archetypes', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('rewards', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── season_chapters ──
    op.create_table(
        'season_chapters',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('season_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('content_seasons.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chapter_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('narrative_intro', sa.Text(), nullable=False, server_default=''),
        sa.Column('unlocks_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scenario_ids', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('challenge_ids', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── xp_events ──
    op.create_table(
        'xp_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('multiplier', sa.Float(), nullable=False, server_default='2.0'),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── New columns on manager_progress ──
    op.add_column('manager_progress', sa.Column('last_drill_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('manager_progress', sa.Column('drill_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('manager_progress', sa.Column('best_drill_streak', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('manager_progress', sa.Column('total_drills', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('manager_progress', sa.Column('league_tier', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('manager_progress', 'league_tier')
    op.drop_column('manager_progress', 'total_drills')
    op.drop_column('manager_progress', 'best_drill_streak')
    op.drop_column('manager_progress', 'drill_streak')
    op.drop_column('manager_progress', 'last_drill_date')
    op.drop_table('xp_events')
    op.drop_table('season_chapters')
    op.drop_table('content_seasons')
    op.drop_table('weekly_league_membership')
    op.drop_table('weekly_league_groups')
    op.drop_table('streak_freezes')
    op.drop_table('goal_completion_log')
