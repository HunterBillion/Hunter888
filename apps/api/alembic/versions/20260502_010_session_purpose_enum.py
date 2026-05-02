"""Session purpose column — distinguish CRM-linked / practice / legacy.

Revision ID: 20260502_010
Revises: 20260502_009
Create Date: 2026-05-02

Why this exists
---------------

Audit FIND-005: 96% of sessions on prod are "orphan" — no
``lead_client_id`` set, so the headline value prop ("coaching tied
to my pipeline") never lands. KPI dashboards / TZ-1 timeline /
session→client coaching feedback all join through ``lead_client_id``
and see ~zero data.

Two diagnostic possibilities for an orphan are conflated today:

  1. The user genuinely wanted **practice** (no client to attribute).
  2. The user wanted to call a real client but didn't pick one
     because the UI defaulted to "free practice".

Both look identical (``lead_client_id IS NULL``). Adding
``session_purpose`` makes intent explicit at start time:

  * ``client_call``  — bound to a CRM client; counts in KPI / timeline
  * ``practice``     — explicit "no client, just practice"; excluded
                       from pipeline KPIs but still shows in personal
                       progress / XP / leaderboard
  * ``legacy_orphan``— historical sessions before this migration; we
                       refuse to retro-attribute (false-match risk
                       too high) and instead label them so dashboards
                       can show "N legacy orphans" as informational.

We use a String column + CHECK constraint instead of a Postgres ENUM
type because (a) extending the catalog later requires no DDL beyond a
constraint replace, (b) the model stays plain ``str``, (c) we already
do this for ``training_sessions.mode`` (see TZ-2 §6.2).

Backfill
--------

Existing rows get ``legacy_orphan`` if ``lead_client_id IS NULL``,
``client_call`` otherwise. Synchronous in this migration so post-
deploy state is consistent in one transaction.

Rollout strategy
----------------

Per agreement (no mandatory walls during pilot):

  * Server-side DEFAULT ``'practice'`` so legacy code paths that don't
    explicitly set the field produce coherent rows.
  * The FE will gain a CHOICE UI on /training start in the same PR,
    defaulting to ``client_call`` when the user has CRM clients.
  * KPI views filter ``WHERE session_purpose = 'client_call'`` to
    show pipeline-attributable work.

Per-user enforcement (``user.preferences.mandatory_client_link``) is
a follow-up flag that can flip ``client_call`` from default to
required without another migration.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260502_010"
down_revision: Union[str, Sequence[str], None] = "20260502_009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ALLOWED = ("client_call", "practice", "legacy_orphan")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Add column. NOT NULL with server-default 'practice' so the
    #    existing rows pass the constraint immediately; we then
    #    backfill the correct values below in the same transaction.
    op.add_column(
        "training_sessions",
        sa.Column(
            "session_purpose",
            sa.String(length=16),
            nullable=False,
            server_default="practice",
        ),
    )

    # 2. CHECK constraint enforces the catalog. Sync with
    #    ``app.models.training.SESSION_PURPOSE_ALLOWED`` and the FE
    #    types — if all three drift, dashboards lie quietly.
    values_sql = ", ".join(repr(v) for v in _ALLOWED)
    op.create_check_constraint(
        "ck_training_sessions_purpose",
        "training_sessions",
        f"session_purpose IN ({values_sql})",
    )

    # 3. Backfill: client_call when there's a lead anchor, otherwise
    #    legacy_orphan. Pre-existing rows from before this migration
    #    are by definition legacy.
    bind.execute(sa.text("""
        UPDATE training_sessions
        SET session_purpose = CASE
            WHEN lead_client_id IS NOT NULL THEN 'client_call'
            ELSE 'legacy_orphan'
        END
    """))

    # 4. Index for the KPI filter — almost every dashboard read
    #    includes session_purpose='client_call', so a btree pays
    #    off fast.
    op.create_index(
        "ix_training_sessions_purpose",
        "training_sessions",
        ["session_purpose"],
    )


def downgrade() -> None:
    op.drop_index("ix_training_sessions_purpose", table_name="training_sessions")
    op.drop_constraint("ck_training_sessions_purpose", "training_sessions", type_="check")
    op.drop_column("training_sessions", "session_purpose")
