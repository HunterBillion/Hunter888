"""S3-03: User subscriptions table for entitlement system.

Creates user_subscriptions table with plan_type, dates, payment refs.
Seeds Master subscriptions for existing seed accounts.

Revision ID: 20260414_005
Revises: 20260414_004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "20260414_005"
down_revision = "20260414_004"
branch_labels = None
depends_on = None

# Seed account emails that get Master plan
SEED_EMAILS = [
    "admin@trainer.local",
    "rop1@trainer.local",
    "rop2@trainer.local",
    "method@trainer.local",
    "manager1@trainer.local",
    "manager2@trainer.local",
    "manager3@trainer.local",
    "manager4@trainer.local",
]


def upgrade() -> None:
    op.create_table(
        "user_subscriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("plan_type", sa.String(20), nullable=False, server_default="scout"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_id", sa.String(255), nullable=True),
        sa.Column("payment_provider", sa.String(50), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"], unique=True)
    op.create_index("ix_user_subscriptions_plan_expires", "user_subscriptions", ["plan_type", "expires_at"])

    # Seed Master subscriptions for existing accounts
    # Using raw SQL to insert based on email lookup
    for email in SEED_EMAILS:
        op.execute(
            sa.text("""
                INSERT INTO user_subscriptions (id, user_id, plan_type, started_at, expires_at)
                SELECT gen_random_uuid(), id, 'master', NOW(), NULL
                FROM users WHERE email = :email
                ON CONFLICT (user_id) DO NOTHING
            """).bindparams(email=email)
        )


def downgrade() -> None:
    op.drop_table("user_subscriptions")
