"""FIND-002 (2026-04-19): sync wiki/xp column+index drift.

Revision ID: 20260419_003
Revises: 20260418_002
Create Date: 2026-04-19

Targeted migration — only the real drift identified by audit. We do NOT
run ``alembic revision --autogenerate`` blindly: the full autogen produces
880+ operations, most cosmetic (NOT NULL/default signature noise) and a
few catastrophic (``drop_table('legal_document')`` would nuke 4400 RAG
rows).

Real changes captured here:

  1. ``wiki_pages.page_type``: VARCHAR(30) → VARCHAR(50). The ORM widened
     the column for new page types but migrations never caught up, so new
     types would silently truncate.

  2. ``wiki_update_log.action``: VARCHAR(30) → VARCHAR(50). Same story.

  3. Index renames on ``xp_log``: old ``ix_xp_log_user`` / ``ix_xp_log_created``
     → new ``ix_xp_log_user_id`` following the ORM column name.

  4. Index cleanups on ``wiki_update_log``: removed a composite index that
     was superseded by per-column indexes the ORM now declares.

CHECK constraint on ``client_profiles.archetype_code`` and a wider audit
pass are deferred to follow-ups.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260419_003"
down_revision = "20260418_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. wiki_pages.page_type widen to 50
    op.alter_column(
        "wiki_pages",
        "page_type",
        existing_type=sa.String(length=30),
        type_=sa.String(length=50),
        existing_nullable=False,
    )

    # 2. wiki_update_log.action widen to 50
    op.alter_column(
        "wiki_update_log",
        "action",
        existing_type=sa.String(length=30),
        type_=sa.String(length=50),
        existing_nullable=False,
    )

    # 3. xp_log: rename user/created composite indexes to match ORM naming.
    # Use IF EXISTS so the migration is idempotent across branches.
    op.execute("DROP INDEX IF EXISTS ix_xp_log_user")
    op.execute("DROP INDEX IF EXISTS ix_xp_log_created")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_xp_log_user_id ON xp_log (user_id)"
    )

    # 4. wiki_update_log: drop superseded composite indexes.
    op.execute("DROP INDEX IF EXISTS ix_wiki_update_log_action_status")
    op.execute("DROP INDEX IF EXISTS ix_wiki_update_log_triggered_by_session_id")


def downgrade() -> None:
    # Reverse order. The widened VARCHARs are safe to shrink back only if
    # no values longer than 30 chars were written meanwhile — we assume
    # that's the case for a rollback within the deploy window.
    op.execute("DROP INDEX IF EXISTS ix_xp_log_user_id")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_xp_log_user ON xp_log (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_xp_log_created ON xp_log (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wiki_update_log_action_status "
        "ON wiki_update_log (action, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wiki_update_log_triggered_by_session_id "
        "ON wiki_update_log (triggered_by_session_id)"
    )

    op.alter_column(
        "wiki_update_log",
        "action",
        existing_type=sa.String(length=50),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
    op.alter_column(
        "wiki_pages",
        "page_type",
        existing_type=sa.String(length=50),
        type_=sa.String(length=30),
        existing_nullable=False,
    )
