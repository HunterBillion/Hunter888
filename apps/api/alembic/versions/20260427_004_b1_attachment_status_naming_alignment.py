"""B1 — align attachments.{ocr_status, classification_status} naming with TZ-4 §7.1.1

Revision ID: 20260427_004
Revises: 20260427_003
Create Date: 2026-04-27

Background
----------

Spec §7.1.1 lists the canonical state-machine values for each of
the four ``Attachment`` status columns. The codebase shipped with
shorthand legacy values that were ambiguous across columns
(``pending`` could mean OCR or classification depending on
context). B1 aligns the writers with the spec; this migration
converts existing rows + bolts on a CHECK constraint so a future
typo cannot land outside the canonical set.

Mapping
-------

Column                   Legacy              →  Spec §7.1.1
``status``               (no change)            uploaded / received / rejected
``ocr_status``           ``pending``         →  ``ocr_pending``
                         ``completed``       →  ``ocr_done``
                         ``failed``          →  ``ocr_failed``
                         ``not_required``       (no change)
``classification_status``  ``pending``       →  ``classification_pending``
                           ``completed``     →  ``classified``
                           ``failed``        →  ``classification_failed``
                           ``not_required``     (no change)
``verification_status``  (no change)            unverified / pending_review /
                                                verified / rejected_review

Re-runnability
--------------

Each ``UPDATE`` is a no-op on rows already at the canonical token,
so re-running the migration on a partial-applied DB doesn't break.
The CHECK constraint is added behind a ``_constraint_exists``
guard.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260427_004"
down_revision: Union[str, Sequence[str], None] = "20260427_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CK_OCR_STATUS = "ck_attachments_ocr_status"
CK_CLASSIFICATION_STATUS = "ck_attachments_classification_status"

OCR_VALUES = ("not_required", "ocr_pending", "ocr_done", "ocr_failed")
CLASSIFICATION_VALUES = (
    "not_required",
    "classification_pending",
    "classified",
    "classification_failed",
)


def _constraint_exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name LIMIT 1"),
            {"name": name},
        ).scalar()
        is not None
    )


def upgrade() -> None:
    bind = op.get_bind()

    # Step 1 — rename legacy ocr_status tokens.
    bind.execute(
        sa.text(
            """
            UPDATE attachments
            SET ocr_status = CASE ocr_status
                WHEN 'pending'   THEN 'ocr_pending'
                WHEN 'completed' THEN 'ocr_done'
                WHEN 'failed'    THEN 'ocr_failed'
                ELSE ocr_status
            END
            WHERE ocr_status IN ('pending', 'completed', 'failed')
            """
        )
    )

    # Step 2 — rename legacy classification_status tokens.
    bind.execute(
        sa.text(
            """
            UPDATE attachments
            SET classification_status = CASE classification_status
                WHEN 'pending'   THEN 'classification_pending'
                WHEN 'completed' THEN 'classified'
                WHEN 'failed'    THEN 'classification_failed'
                ELSE classification_status
            END
            WHERE classification_status IN ('pending', 'completed', 'failed')
            """
        )
    )

    # Step 3 — sanity check: refuse to add CHECK if any rows still
    # carry non-canonical values. Surfaces the inconsistency loudly
    # instead of silently failing the ALTER.
    ocr_bad = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM attachments "
            f"WHERE ocr_status NOT IN {OCR_VALUES}"
        )
    ).scalar_one()
    if ocr_bad and int(ocr_bad) > 0:
        raise RuntimeError(
            f"Cannot add CHECK on attachments.ocr_status: "
            f"{ocr_bad} rows still hold non-canonical values."
        )

    cls_bad = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM attachments "
            f"WHERE classification_status NOT IN {CLASSIFICATION_VALUES}"
        )
    ).scalar_one()
    if cls_bad and int(cls_bad) > 0:
        raise RuntimeError(
            f"Cannot add CHECK on attachments.classification_status: "
            f"{cls_bad} rows still hold non-canonical values."
        )

    # Step 4 — add CHECK constraints (idempotent).
    if not _constraint_exists(CK_OCR_STATUS):
        op.create_check_constraint(
            CK_OCR_STATUS,
            "attachments",
            f"ocr_status IN {OCR_VALUES}",
        )
    if not _constraint_exists(CK_CLASSIFICATION_STATUS):
        op.create_check_constraint(
            CK_CLASSIFICATION_STATUS,
            "attachments",
            f"classification_status IN {CLASSIFICATION_VALUES}",
        )


def downgrade() -> None:
    if _constraint_exists(CK_CLASSIFICATION_STATUS):
        op.drop_constraint(
            CK_CLASSIFICATION_STATUS, "attachments", type_="check"
        )
    if _constraint_exists(CK_OCR_STATUS):
        op.drop_constraint(CK_OCR_STATUS, "attachments", type_="check")

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE attachments
            SET ocr_status = CASE ocr_status
                WHEN 'ocr_pending' THEN 'pending'
                WHEN 'ocr_done'    THEN 'completed'
                WHEN 'ocr_failed'  THEN 'failed'
                ELSE ocr_status
            END
            WHERE ocr_status IN ('ocr_pending', 'ocr_done', 'ocr_failed')
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE attachments
            SET classification_status = CASE classification_status
                WHEN 'classification_pending' THEN 'pending'
                WHEN 'classified'             THEN 'completed'
                WHEN 'classification_failed'  THEN 'failed'
                ELSE classification_status
            END
            WHERE classification_status IN
                ('classification_pending', 'classified', 'classification_failed')
            """
        )
    )
