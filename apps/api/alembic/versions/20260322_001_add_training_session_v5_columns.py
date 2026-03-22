"""Add ORM columns on training_sessions that were never migrated (v5).

score_human_factor, score_narrative, score_legal, client_story_id, call_number_in_story
were in SQLAlchemy but missing from Alembic — inserts failed against DBs created only via migrations.

Uses IF NOT EXISTS so DBs that already have these columns (e.g. create_all) stay valid.

Revision ID: 20260322_001
Revises: 20260321_003
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260322_001"
down_revision: Union[str, None] = "20260321_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS score_human_factor DOUBLE PRECISION"
    ))
    op.execute(sa.text(
        "ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS score_narrative DOUBLE PRECISION"
    ))
    op.execute(sa.text(
        "ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS score_legal DOUBLE PRECISION"
    ))
    op.execute(sa.text(
        "ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS client_story_id UUID"
    ))
    op.execute(sa.text(
        "ALTER TABLE training_sessions ADD COLUMN IF NOT EXISTS call_number_in_story INTEGER"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_training_sessions_client_story_id "
        "ON training_sessions (client_story_id)"
    ))
    op.execute(sa.text("""
        DO $$ BEGIN
            ALTER TABLE training_sessions
                ADD CONSTRAINT fk_training_sessions_client_story_id_client_stories
                FOREIGN KEY (client_story_id) REFERENCES client_stories(id) ON DELETE SET NULL;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$
    """))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE training_sessions DROP CONSTRAINT IF EXISTS "
        "fk_training_sessions_client_story_id_client_stories"
    ))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_training_sessions_client_story_id"))
    for col in (
        "call_number_in_story",
        "client_story_id",
        "score_legal",
        "score_narrative",
        "score_human_factor",
    ):
        op.execute(sa.text(f"ALTER TABLE training_sessions DROP COLUMN IF EXISTS {col}"))
