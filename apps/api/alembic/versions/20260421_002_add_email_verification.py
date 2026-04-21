"""Add email_verified flag and email_verification_token to users

Revision ID: 20260421_002
Revises: 20260421_001
Create Date: 2026-04-21

Adds two columns to users:
  - email_verified (bool, default false) — flips to true on token click
  - email_verification_sent_at (timestamptz) — for rate limiting resend,
    null means no verification email sent yet

Verification tokens themselves are stored in Redis (short TTL, auto-expire),
not in the users table — keeps the schema light and makes revoke trivial.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260421_002"
down_revision = "20260421_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent via DO block — safe on re-run
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE users
              ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT false;
            ALTER TABLE users
              ADD COLUMN IF NOT EXISTS email_verification_sent_at TIMESTAMPTZ NULL;
        EXCEPTION
            WHEN undefined_table THEN NULL;
        END $$;
        """
    )
    # Existing OAuth users should be auto-verified (their email is trusted by
    # Google/Yandex). Runs only once since this migration is forward-only.
    op.execute(
        """
        UPDATE users
        SET email_verified = true
        WHERE (google_id IS NOT NULL OR yandex_id IS NOT NULL)
          AND email_verified = false;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verification_sent_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS email_verified")
