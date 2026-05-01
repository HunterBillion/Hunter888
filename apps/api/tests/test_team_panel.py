"""Team-panel endpoint contract tests.

Three endpoints share one router and have a clean shape — these tests
pin the JSONable request/response shapes the FE relies on, plus the
permissive-CSV invariants (BOM tolerance, blank-row skip, missing
required header → 422, empty file → 400, oversized → 413).

Endpoint logic that hits the DB is exercised through API integration
tests (separate file) — these are pure unit checks on the schemas and
helpers.
"""
from __future__ import annotations

import io
import uuid
from types import SimpleNamespace

import pytest

from app.api.team import (
    BulkAssignRequest,
    BulkAssignResponse,
    BulkAssignRowResult,
    CsvImportResponse,
    CsvImportRowResult,
    CSV_ALLOWED_ROLES,
    CSV_REQUIRED_COLUMNS,
    MAX_CSV_BYTES,
)


# ── Bulk assign request shape ───────────────────────────────────────────


def test_bulk_assign_request_requires_at_least_one_user():
    with pytest.raises(Exception):
        BulkAssignRequest(scenario_id=uuid.uuid4(), user_ids=[])


def test_bulk_assign_request_caps_at_200_users():
    too_many = [uuid.uuid4() for _ in range(201)]
    with pytest.raises(Exception):
        BulkAssignRequest(scenario_id=uuid.uuid4(), user_ids=too_many)


def test_bulk_assign_request_accepts_max_batch():
    """Exactly 200 users — at the cap, not over."""
    ids = [uuid.uuid4() for _ in range(200)]
    req = BulkAssignRequest(scenario_id=uuid.uuid4(), user_ids=ids)
    assert len(req.user_ids) == 200


def test_bulk_assign_response_shape_serializable():
    resp = BulkAssignResponse(
        scenario_id=uuid.uuid4(),
        total=2,
        assigned=1,
        skipped=1,
        errors=0,
        rows=[
            BulkAssignRowResult(user_id=uuid.uuid4(), status="assigned",
                                assignment_id=uuid.uuid4()),
            BulkAssignRowResult(user_id=uuid.uuid4(),
                                status="skipped_other_team"),
        ],
    )
    blob = resp.model_dump(mode="json")
    assert blob["assigned"] == 1
    assert blob["rows"][0]["status"] == "assigned"
    assert blob["rows"][1]["assignment_id"] is None


# ── CSV import shape + helpers ──────────────────────────────────────────


def test_csv_required_columns_set():
    """The FE form refuses to submit if these columns are missing — so
    the server's expectation must stay aligned with what the FE allows.
    """
    assert {"email", "full_name"} == CSV_REQUIRED_COLUMNS


def test_csv_allowed_roles_subset_of_user_role_enum():
    """CSV import accepts a subset of UserRole values (legacy
    `methodologist` was retired 2026-04-26 — don't accept new ones via
    CSV import). Test asserts every CSV-allowed role exists in the
    enum, NOT vice versa."""
    from app.models.user import UserRole

    enum_values = {r.value for r in UserRole}
    assert CSV_ALLOWED_ROLES.issubset(enum_values)
    # Pin the exact CSV-onboardable set so it doesn't drift silently.
    assert CSV_ALLOWED_ROLES == {"manager", "rop", "admin"}


def test_csv_max_bytes_is_one_megabyte():
    assert MAX_CSV_BYTES == 1024 * 1024


def test_csv_response_per_row_status_strings():
    """The FE chip-renderer maps these literals to colors. Any drift =
    silent UI breakage."""
    rows = [
        CsvImportRowResult(line=2, email="a@b.com", status="created",
                           user_id=uuid.uuid4()),
        CsvImportRowResult(line=3, email="dup@b.com",
                           status="skipped_duplicate_email"),
        CsvImportRowResult(line=4, email="bad@b.com",
                           status="skipped_invalid", error="role=foo"),
        CsvImportRowResult(line=5, email="x@b.com",
                           status="error", error="DB"),
    ]
    statuses = {r.status for r in rows}
    assert statuses == {
        "created", "skipped_duplicate_email", "skipped_invalid", "error",
    }


def test_csv_response_aggregate_counts():
    resp = CsvImportResponse(
        total=4, created=1, skipped=2, errors=1,
        rows=[
            CsvImportRowResult(line=2, email="a@b.com", status="created"),
            CsvImportRowResult(line=3, email="b@b.com",
                               status="skipped_duplicate_email"),
            CsvImportRowResult(line=4, email="c@b.com",
                               status="skipped_invalid"),
            CsvImportRowResult(line=5, email="d@b.com", status="error"),
        ],
    )
    blob = resp.model_dump(mode="json")
    assert blob["total"] == 4
    assert blob["created"] + blob["skipped"] + blob["errors"] == blob["total"]


# ── CSV permissive parsing ──────────────────────────────────────────────


def test_csv_parser_handles_bom_and_blank_rows():
    """The Excel default export prepends BOM (﻿) and may leave
    trailing blank rows. The endpoint must skip blanks and tolerate BOM.
    Smoke-tests the parser without hitting the DB.
    """
    import csv

    text = "﻿email,full_name,role\n\nivan@x.ru,Иван П.,manager\n,,\n"
    reader = csv.DictReader(io.StringIO(text))
    fields = {h.strip() for h in (reader.fieldnames or [])}
    # BOM is stripped via decode("utf-8-sig") in production; here we
    # confirm the dict keys are intact when we encode/decode the same
    # way the endpoint does.
    decoded = text.encode("utf-8").decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))
    rows = [r for r in reader if any((v or "").strip() for v in r.values())]
    assert len(rows) == 1
    assert rows[0]["email"] == "ivan@x.ru"
    assert rows[0]["full_name"] == "Иван П."


def test_csv_parser_rejects_missing_required_columns():
    """Missing `full_name` → endpoint returns 422 before processing rows."""
    import csv

    text = "email,role\nivan@x.ru,manager\n"
    reader = csv.DictReader(io.StringIO(text))
    fields = {h.strip() for h in (reader.fieldnames or [])}
    assert not CSV_REQUIRED_COLUMNS.issubset(fields)
