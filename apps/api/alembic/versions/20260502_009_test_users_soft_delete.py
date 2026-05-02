"""Soft-delete test/audit users polluting KPI dashboards.

Revision ID: 20260502_009
Revises: 20260502_008
Create Date: 2026-05-02

Why this exists
---------------

Audit 2026-05-02 (FIND-009) found that ~56% of `users` rows on prod are
auto-registered test artefacts from CSRF/audit/probe/stress tests
that hit `/auth/register` directly:

  * audit*@test.com         (~6 rows)  — audit smoke tests
  * a*@test.com / u*@test.com / user*@test.com  (~6) — short aliases
  * csrf*/replay*/stress*@test.com   (~5)  — load tests
  * probe*@test.local       (~12) — TZ-2 probes
  * test*@test.com          (1)

All have `0 sessions, 0 pvp, 0 ratings, 0 xp, 0 analytics_events` on
prod (verified 2026-05-02). They DO own 4 lead_clients / 4
real_clients ("Probe Client", "TZ2 Test Client") which are themselves
test data — those are also soft-deleted here.

KPI dashboards (`leaderboard`, `team_kpi`, `manager_progress`)
already filter `WHERE users.is_active = true` for live queries, so
soft-delete (this migration) cleans the numbers without touching
sessions / FK history / 152-FZ consents. Cached aggregates
(`LeaderboardSnapshot`, `WeeklyReport`) refresh on their cron and
will pick up the change within a day.

Whitelist
---------

Two classes of accounts are EXCLUDED from soft-delete:

  1. ``*@trainer.local`` — operator's manual test accounts (8 rows:
     admin / rop1 / rop2 / method / manager1..4). These look similar
     to test artefacts but are deliberately kept for ROP-side smoke
     testing of dashboards under multiple roles.
  2. ``google_id IS NOT NULL`` — any user who logged in via Google
     OAuth. By construction the email is real (Google verified it),
     even if it happens to contain the substring "test".

Reversibility
-------------

`downgrade()` restores `is_active=true` and original email by
stripping the `.deleted-<timestamp>` suffix. Idempotent — re-running
upgrade after downgrade re-applies the rule.

For the lead_clients / real_clients we mark `is_active=false` (the
column exists on RealClient via the consent + lifecycle model) and
leave the FK to the soft-deleted manager intact. The FK is
``ondelete=RESTRICT`` so we couldn't hard-delete the manager anyway
without orphaning these rows; soft-delete is the correct shape.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260502_009"
down_revision: Union[str, Sequence[str], None] = "20260502_008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Single source of truth for the test-pattern. Mirrors the SELECT used
# in the dry-run query so the count we report (29) matches what we
# actually mutate.
_TEST_PATTERN_WHERE = """
    (
        email ~* '@(test|fulltest|csrf|audit)'
        OR email LIKE 'audit_%@%'
        OR email LIKE 'csrf%@test.%'
    )
    AND email NOT LIKE '%@trainer.local'
    AND google_id IS NULL
    AND is_active = true
"""

# Suffix tag — embeds the migration date so a future repeat sweep
# doesn't double-tag (idempotency check in upgrade).
_DELETED_SUFFIX = '.deleted-2026-05-02'


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Soft-delete users matching the test-pattern.
    #    UNIQUE constraint on email forces us to rename: append a
    #    timestamp suffix so the original email becomes available again
    #    and the row survives the UPDATE without conflict.
    bind.execute(sa.text(f"""
        UPDATE users
        SET
            is_active = false,
            email = email || :suffix
        WHERE
            {_TEST_PATTERN_WHERE}
            -- Don't double-tag if migration ran before
            AND email NOT LIKE '%' || :suffix
    """), {"suffix": _DELETED_SUFFIX})

    # 2. Soft-delete the test real_clients owned by those users.
    #    `is_active` exists on real_clients per the schema. After this
    #    UPDATE the soft-deleted manager still owns soft-deleted clients
    #    — both are filtered out by KPI views.
    bind.execute(sa.text("""
        UPDATE real_clients
        SET is_active = false
        WHERE manager_id IN (
            SELECT id FROM users
            WHERE email LIKE '%' || :suffix
              AND is_active = false
        )
    """), {"suffix": _DELETED_SUFFIX})


def downgrade() -> None:
    bind = op.get_bind()

    # 1. Restore real_clients
    bind.execute(sa.text("""
        UPDATE real_clients
        SET is_active = true
        WHERE manager_id IN (
            SELECT id FROM users
            WHERE email LIKE '%' || :suffix
              AND is_active = false
        )
    """), {"suffix": _DELETED_SUFFIX})

    # 2. Restore users — strip suffix, flip is_active back.
    bind.execute(sa.text("""
        UPDATE users
        SET
            is_active = true,
            email = REPLACE(email, :suffix, '')
        WHERE
            is_active = false
            AND email LIKE '%' || :suffix
    """), {"suffix": _DELETED_SUFFIX})
