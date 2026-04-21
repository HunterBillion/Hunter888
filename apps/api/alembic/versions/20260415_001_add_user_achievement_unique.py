"""Add unique constraint on user_achievements(user_id, achievement_id).

Revision ID: 20260415_001
Revises: 20260414_006
Create Date: 2026-04-15
"""
from alembic import op

revision = "20260415_001"
down_revision = "20260414_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First, remove any existing duplicates (keep the earliest one)
    op.execute("""
        DELETE FROM user_achievements
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id, achievement_id) id
            FROM user_achievements
            ORDER BY user_id, achievement_id, created_at
        )
    """)
    op.create_unique_constraint(
        "uq_user_achievement",
        "user_achievements",
        ["user_id", "achievement_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_achievement", "user_achievements", type_="unique")
