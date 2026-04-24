"""Add unique constraint on user_achievements(user_id, achievement_id).

Revision ID: 20260415_001
Revises: 20260414_006
Create Date: 2026-04-15
"""
import sqlalchemy as sa
from alembic import op

revision = "20260415_001"
down_revision = "20260414_006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First, remove any existing duplicates (keep the earliest one).
    # ``initial_schema`` created this table with ``earned_at``, not
    # ``created_at`` — the original migration referenced a column that
    # never existed on a fresh DB and CI failed as soon as it ran.
    # We probe the actual column name at migration time so this still
    # works on prod DBs that may have been hand-patched to include
    # ``created_at``.
    conn = op.get_bind()
    cols = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'user_achievements'"
            )
        )
    }
    order_column = "earned_at" if "earned_at" in cols else "created_at"
    conn.execute(
        sa.text(
            f"""
            DELETE FROM user_achievements
            WHERE id NOT IN (
                SELECT DISTINCT ON (user_id, achievement_id) id
                FROM user_achievements
                ORDER BY user_id, achievement_id, {order_column}
            )
            """
        )
    )
    op.create_unique_constraint(
        "uq_user_achievement",
        "user_achievements",
        ["user_id", "achievement_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_user_achievement", "user_achievements", type_="unique")
