"""TZ-1 §8 status lattice — DB-level CHECK on LeadClient.

Revision ID: 20260425_003
Revises: 20260425_002
Create Date: 2026-04-25

Adds CHECK constraints so ``lead_clients.lifecycle_stage`` and
``lead_clients.work_state`` cannot accept anything outside the canonical
catalog. Before this, the columns were free ``String(40)`` and any
``lead.lifecycle_stage = "garbage"`` would persist — which the deep
audit (A-finding §8) flagged as a real lattice integrity hole.

Pre-flight:
  - sanitize any rows that already drifted (defensive: prod was clean
    at audit time, but a re-run on staging or a future bad migration
    could leave junk; we coerce unknowns back to safe defaults so the
    constraint doesn't break ``alembic upgrade head``).
  - then add NOT VALID first (won't lock long), then VALIDATE so the
    final state is a fully-trusted constraint.

Down migration drops the constraints only — it does not try to
re-introduce drifted values.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260425_003"
down_revision: Union[str, Sequence[str], None] = "20260425_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_LIFECYCLE_VALUES = (
    "new", "contacted", "interested", "consultation", "thinking",
    "consent_received", "contract_signed", "documents_in_progress",
    "case_in_progress", "completed", "lost",
)
_WORK_STATE_VALUES = (
    "active", "callback_scheduled", "waiting_client", "waiting_documents",
    "consent_pending", "paused", "consent_revoked", "duplicate_review",
    "archived",
)


def _quoted(values: Sequence[str]) -> str:
    return ",".join(f"'{v}'" for v in values)


def upgrade() -> None:
    bind = op.get_bind()

    # Coerce drifted rows to safe defaults so VALIDATE won't fail. This is
    # idempotent — clean rows are untouched.
    bind.execute(
        f"UPDATE lead_clients SET lifecycle_stage = 'new' "
        f"WHERE lifecycle_stage NOT IN ({_quoted(_LIFECYCLE_VALUES)})"
    )
    bind.execute(
        f"UPDATE lead_clients SET work_state = 'active' "
        f"WHERE work_state NOT IN ({_quoted(_WORK_STATE_VALUES)})"
    )

    # NOT VALID first → no full-table scan / lock. Then VALIDATE picks up
    # only what existing data already satisfies (post-coercion above).
    op.execute(
        f"ALTER TABLE lead_clients ADD CONSTRAINT ck_lead_clients_lifecycle_stage "
        f"CHECK (lifecycle_stage IN ({_quoted(_LIFECYCLE_VALUES)})) NOT VALID"
    )
    op.execute(
        f"ALTER TABLE lead_clients ADD CONSTRAINT ck_lead_clients_work_state "
        f"CHECK (work_state IN ({_quoted(_WORK_STATE_VALUES)})) NOT VALID"
    )
    op.execute("ALTER TABLE lead_clients VALIDATE CONSTRAINT ck_lead_clients_lifecycle_stage")
    op.execute("ALTER TABLE lead_clients VALIDATE CONSTRAINT ck_lead_clients_work_state")


def downgrade() -> None:
    op.execute("ALTER TABLE lead_clients DROP CONSTRAINT IF EXISTS ck_lead_clients_lifecycle_stage")
    op.execute("ALTER TABLE lead_clients DROP CONSTRAINT IF EXISTS ck_lead_clients_work_state")
