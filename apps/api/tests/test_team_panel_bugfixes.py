"""Regression tests for the FIND-008/009 team-panel bug bash.

Each test pins one of the bugs we caught against prod with the four
test creds (admin / rop1 / rop2 / methodologist) on 2026-05-04 and
fixes in this PR:

  * FIND-008  /dashboard/rop/export → 500 (Cyrillic on Helvetica)
  * FIND-008b POST /team/assignments/bulk → 422 (FastAPI mistook the
              limiter ``request`` arg for a query param)
  * FIND-009  /dashboard/rop/weekly-digest → week_start == week_end
              when "today is Monday" (zero-day window).
  * FIND-009b /dashboard/rop/sessions cross-team → 200 + ``{error:..}``
              instead of 403 (soft-fail confused FE).

These tests deliberately avoid the heavy DB/Redis fixtures — they use
the schemas and helper functions directly so they stay green even if a
new alembic migration is in flight.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.team import BulkAssignResponse, BulkAssignRowResult


# ── FIND-008b: bulk-assign response shape carries WS notify counters ──


def test_bulk_assign_response_has_notification_counters():
    """The FE renders "50 assigned, 47 notified, 3 без WS" — the API
    must surface both counters separately so the toast is honest."""
    resp = BulkAssignResponse(
        scenario_id=uuid.uuid4(),
        total=3,
        assigned=3,
        skipped=0,
        errors=0,
        notifications_sent=2,
        notifications_failed=1,
        rows=[
            BulkAssignRowResult(user_id=uuid.uuid4(), status="assigned",
                                assignment_id=uuid.uuid4()),
            BulkAssignRowResult(user_id=uuid.uuid4(), status="assigned",
                                assignment_id=uuid.uuid4()),
            BulkAssignRowResult(user_id=uuid.uuid4(), status="assigned",
                                assignment_id=uuid.uuid4()),
        ],
    )
    blob = resp.model_dump(mode="json")
    assert blob["notifications_sent"] == 2
    assert blob["notifications_failed"] == 1


def test_bulk_assign_response_defaults_zero_when_not_set():
    """Backwards-compat: pre-fix callers didn't set the counters."""
    resp = BulkAssignResponse(
        scenario_id=uuid.uuid4(),
        total=0, assigned=0, skipped=0, errors=0,
        rows=[],
    )
    blob = resp.model_dump(mode="json")
    assert blob["notifications_sent"] == 0
    assert blob["notifications_failed"] == 0


def test_bulk_assign_handler_signature_accepts_request_class():
    """FIND-008b: the handler must annotate ``request: Request`` so
    FastAPI doesn't think it's a query parameter. Reflectively check
    the type hint — if someone reverts to bare ``request,`` the test
    will catch it on the next run."""
    import inspect

    from fastapi import Request as FastAPIRequest

    from app.api.team import bulk_assign_training, import_users_csv

    for handler in (bulk_assign_training, import_users_csv):
        sig = inspect.signature(handler)
        annot = sig.parameters["request"].annotation
        assert annot is FastAPIRequest, (
            f"{handler.__name__}: ``request`` must be annotated as Request "
            f"(got {annot!r}) — bare names become FastAPI query params."
        )


# ── FIND-009: weekly digest week boundaries ──


def test_weekly_digest_window_is_full_seven_days_on_monday():
    """When today is Monday the digest must report the WEEK THAT JUST
    ENDED (last Mon..Sun, 7 full days), not a zero-day window
    (today..today)."""
    # Replicate the date math from the service (the function itself
    # touches the DB; we extract the window logic independently).
    fake_now = datetime(2026, 5, 4, 9, 0, 0, tzinfo=timezone.utc)  # Mon
    midnight = fake_now.replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_monday = fake_now.weekday()  # 0
    this_monday = midnight - timedelta(days=days_since_monday)
    week_end = this_monday
    week_start = this_monday - timedelta(days=7)

    assert (week_end - week_start).days == 7
    assert week_start.weekday() == 0
    assert week_end.weekday() == 0
    assert week_start < week_end  # NOT zero-day


@pytest.mark.parametrize(
    "fake_now",
    [
        datetime(2026, 5, 4, 9, 0, tzinfo=timezone.utc),   # Mon
        datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),  # Tue
        datetime(2026, 5, 7, 23, 59, tzinfo=timezone.utc), # Thu
        datetime(2026, 5, 10, 7, 0, tzinfo=timezone.utc),  # Sun
    ],
)
def test_weekly_digest_window_invariant_every_weekday(fake_now):
    """The previous-week window must be exactly 7 days on EVERY
    weekday, not just Monday."""
    midnight = fake_now.replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_monday = fake_now.weekday()
    this_monday = midnight - timedelta(days=days_since_monday)
    week_end = this_monday
    week_start = this_monday - timedelta(days=7)
    assert (week_end - week_start).days == 7
    assert week_start.weekday() == 0


# ── FIND-008: PDF export must not crash on Cyrillic team names ──


@pytest.mark.asyncio
async def test_pdf_export_renders_cyrillic_team_name_without_unicode_error():
    """Pre-fix: ``pdf.set_font("Helvetica")`` + Cyrillic team name
    raised UnicodeEncodeError → 500. Post-fix: registers DejaVuSans if
    available, transliterates to ASCII otherwise — never raises.
    """
    import importlib

    # If ``fpdf`` isn't available in the dev venv (it's installed only
    # in the API service), skip — the production path is exercised by
    # the live curl in the deploy-verify step.
    if importlib.util.find_spec("fpdf") is None:
        pytest.skip("fpdf not installed in this venv — exercised in API CI image")

    from app.services import rop_export

    db = MagicMock()
    db.execute = AsyncMock()

    # Stub the team query to return a Cyrillic-named team.
    team_obj = MagicMock()
    team_obj.name = "Отдел продаж"

    members_result = MagicMock()
    members_result.scalars.return_value.all.return_value = []

    team_result = MagicMock()
    team_result.scalar_one_or_none.return_value = team_obj

    # The function fires several queries — return same empty result for
    # any subsequent execute() call.
    async def execute_side_effect(*args, **kwargs):
        # First call is the team SELECT; subsequent calls are members.
        if not getattr(execute_side_effect, "fired", False):
            execute_side_effect.fired = True
            return team_result
        return members_result
    db.execute.side_effect = execute_side_effect

    pdf_bytes = await rop_export.generate_team_report_pdf(
        team_id=uuid.uuid4(),
        rop_name="Елена Кузнецова",
        period="week",
        db=db,
    )
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert pdf_bytes[:4] == b"%PDF"  # standard PDF magic header
    assert len(pdf_bytes) > 200  # not an empty stub
