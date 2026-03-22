"""Add OAuth fields (google_id, yandex_id) to users table.

Revision ID: d4e5f6a7b8c9
Revises: c863e49a439a
Create Date: 2026-03-20 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c863e49a439a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("yandex_id", sa.String(255), nullable=True))
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    op.create_index("ix_users_yandex_id", "users", ["yandex_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_yandex_id", table_name="users")
    op.drop_index("ix_users_google_id", table_name="users")
    op.drop_column("users", "yandex_id")
    op.drop_column("users", "google_id")
