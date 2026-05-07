"""Backfill default top_rewards on the currently-active season

Revision ID: 20260507_003
Revises: 20260507_002
Create Date: 2026-05-07

The PvPSeason.top_rewards column was added in 20260507_001 and the
scheduler now stamps default values on every new season (PR-10). But
the CURRENTLY ACTIVE season was created before either change — its
``top_rewards`` is NULL, which means the /pvp slim hero banner shows
"Сезон до 31 мая" with no «топ-1» line.

This migration backfills any active season that has NULL top_rewards
with the same default the scheduler now writes (top-3, magnitudes
calibrated for the pilot audience). Methodologists can overwrite
per-season via POST /api/pvp/admin/season/create.

Idempotent:
  - WHERE top_rewards IS NULL — only touches rows without explicit values
  - WHERE is_active = TRUE — methodologists' historical custom rewards
    on already-ended seasons stay untouched

Downgrade is a no-op on data — column drop happens in 20260507_001 if
the chain is rolled back further.
"""
from __future__ import annotations

import json

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260507_003"
down_revision = "20260507_002"
branch_labels = None
depends_on = None


_DEFAULT = json.dumps([
    {"rank": 1, "ap": 100, "badge": "champion-of-the-month"},
    {"rank": 2, "ap": 60,  "badge": "silver-stand"},
    {"rank": 3, "ap": 30,  "badge": "bronze-stand"},
])


def upgrade() -> None:
    op.execute(f"""
        UPDATE pvp_seasons
           SET top_rewards = '{_DEFAULT}'::jsonb
         WHERE is_active = TRUE
           AND top_rewards IS NULL;
    """)


def downgrade() -> None:
    # Reverse only the rows we set (those that still match the default).
    op.execute(f"""
        UPDATE pvp_seasons
           SET top_rewards = NULL
         WHERE is_active = TRUE
           AND top_rewards = '{_DEFAULT}'::jsonb;
    """)
