"""PvP season + Tournament is_active backfill (B5-03, B5-10).

Revision ID: 20260502_007
Revises: 20260502_006
Create Date: 2026-05-02

Why this exists
---------------

Two orthogonal infrastructure issues found by the 2026-05-02 audit, fixed
in one migration because they share the same observable outcome (broken
PvP/tournament UX) and the same idempotency contract.

**B5-03 — no active PvP season.** ``/api/pvp/season/active`` returned
``null`` on prod, with no row in ``pvp_seasons`` flagged ``is_active``.
The auto-create cron (``services/scheduler.py:243-301``
``_check_seasonal_pvp_reset``) fires only on the 1st of the month
00:00-00:59 UTC; if a deploy gap or worker hiccup misses that window,
the platform sits without a season for the entire month. Ratings
keep updating (``glicko2.update_rating`` does not require a season),
but ``leaderboard.season`` shows ``null`` and end-of-season-rewards
cannot fire. The fix: insert a current-month season if none active.

**B5-10 — Tournament is_active=null on in-window rows.** A few legacy
INSERT paths bypass the SQLAlchemy ORM default and never set the
``is_active`` field. ``Tournament.is_active`` had a Python default
(``default=True``) but no ``server_default`` until this migration —
so any direct SQL or admin-script that omitted the column landed
with NULL. Postgres won't return NULL == True, so
``services.tournament.get_active_tournament`` filters them out and
the FE shows "no active tournament" while one is sitting in the
table.

Operations
----------

1. **De-dup active seasons.** If multiple rows have ``is_active=true``
   (incident leftover), keep only the most recent. Pre-fix data,
   no-op when the table already has at most one.
2. **Insert current-month season** if none active. Calculated as
   ``[date_trunc('month', now()), end_of_month - 1 second]`` so the
   row aligns with the cron's expected boundary. Insert is guarded
   by ``WHERE NOT EXISTS`` so re-runs never create duplicates.
3. **Tournaments backfill.** UPDATE in-window rows whose
   ``is_active`` is NULL to TRUE. UPDATE expired rows whose
   ``is_active`` is NULL to FALSE. Both predicates are conservative —
   they never overwrite an explicit value (true OR false).
4. **NOT NULL + server_default on `tournaments.is_active`.** After
   step 3 has populated every row, promote the column so future
   raw INSERTs cannot regenerate the same bug.
5. **NOT NULL + server_default on `pvp_seasons.is_active`.** Same
   protection for the season table. Existing rows are already
   non-NULL after step 1's dedup so the constraint applies cleanly.
6. **Unique partial index ``uq_one_active_pvp_season``** on
   ``pvp_seasons (is_active) WHERE is_active = TRUE``. Belt + suspenders
   so a future race in season-creation can never produce the
   ambiguous "two active seasons" state again.

Reversibility
-------------

``downgrade()`` reverses 4 + 5 (drop NOT NULL + server_default) and
drops the unique index. The data backfilled in 1-3 is left as-is —
those rows were going to land that way anyway once the system caught
up; rolling back the migration shouldn't undo the team's accumulated
season + tournament state.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260502_007"
down_revision: Union[str, Sequence[str], None] = "20260502_006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── Step 1: de-dup active seasons ──────────────────────────────────
    # If two or more rows have is_active=true (operational leftover),
    # keep the most recent (max start_date) and demote the rest. Idempotent
    # — single-row case is a no-op.
    bind.execute(
        sa.text(
            """
            UPDATE pvp_seasons
            SET is_active = FALSE
            WHERE is_active = TRUE
              AND id NOT IN (
                  SELECT id FROM pvp_seasons
                  WHERE is_active = TRUE
                  ORDER BY start_date DESC
                  LIMIT 1
              )
            """
        )
    )

    # ── Step 2: ensure one current-month season exists ─────────────────
    # Computed bounds: [first day of current month, last day of current
    # month at 23:59:59]. The Russian-locale name ("Сезон <Месяц YYYY>")
    # matches the cron's naming style at scheduler.py:268.
    bind.execute(
        sa.text(
            """
            INSERT INTO pvp_seasons (
                id, name, start_date, end_date, is_active, rewards
            )
            SELECT
                gen_random_uuid(),
                'Сезон ' || to_char(date_trunc('month', now()), 'TMMonth YYYY'),
                date_trunc('month', now()),
                date_trunc('month', now()) + interval '1 month' - interval '1 second',
                TRUE,
                '{}'::jsonb
            WHERE NOT EXISTS (
                SELECT 1 FROM pvp_seasons WHERE is_active = TRUE
            )
            """
        )
    )

    # ── Step 3a: tournaments — backfill in-window NULLs to TRUE ───────
    bind.execute(
        sa.text(
            """
            UPDATE tournaments
            SET is_active = TRUE
            WHERE is_active IS NULL
              AND week_start <= NOW()
              AND week_end >= NOW()
            """
        )
    )

    # ── Step 3b: tournaments — backfill expired NULLs to FALSE ────────
    bind.execute(
        sa.text(
            """
            UPDATE tournaments
            SET is_active = FALSE
            WHERE is_active IS NULL
              AND week_end < NOW()
            """
        )
    )

    # ── Step 3c: tournaments — backfill future-window NULLs to FALSE ──
    # Tournaments registered ahead of their week (e.g. cron setting up
    # next week's sprint on Sunday night) get is_active=FALSE until the
    # next-Monday cron flips them. Any remaining NULL after 3a/3b lands
    # in this branch — should be future tournaments.
    bind.execute(
        sa.text("UPDATE tournaments SET is_active = FALSE WHERE is_active IS NULL")
    )

    # ── Step 4: tournaments — NOT NULL + server_default ───────────────
    op.execute(
        sa.text(
            "ALTER TABLE tournaments "
            "ALTER COLUMN is_active SET DEFAULT TRUE"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE tournaments "
            "ALTER COLUMN is_active SET NOT NULL"
        )
    )

    # ── Step 5: pvp_seasons — NOT NULL + server_default ───────────────
    op.execute(
        sa.text(
            "ALTER TABLE pvp_seasons "
            "ALTER COLUMN is_active SET DEFAULT TRUE"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE pvp_seasons "
            "ALTER COLUMN is_active SET NOT NULL"
        )
    )

    # ── Step 6: unique partial index — at-most-one-active invariant ───
    # Postgres-specific. Without this, a future race between
    # ``_check_seasonal_pvp_reset`` and an admin POST could create two
    # active seasons; consumers that ``LIMIT 1`` would pick non-
    # deterministically. The partial index is a hard wall.
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_pvp_season "
            "ON pvp_seasons (is_active) WHERE is_active = TRUE"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_one_active_pvp_season"))
    op.execute(
        sa.text("ALTER TABLE pvp_seasons ALTER COLUMN is_active DROP NOT NULL")
    )
    op.execute(
        sa.text("ALTER TABLE pvp_seasons ALTER COLUMN is_active DROP DEFAULT")
    )
    op.execute(
        sa.text("ALTER TABLE tournaments ALTER COLUMN is_active DROP NOT NULL")
    )
    op.execute(
        sa.text("ALTER TABLE tournaments ALTER COLUMN is_active DROP DEFAULT")
    )
    # Backfilled data rows are intentionally not reverted — they
    # represent the team's actual season/tournament state.
