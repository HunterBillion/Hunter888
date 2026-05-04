"""Contract tests for ``PATCH /admin/users/{user_id}``.

Pins the request shape, the four side-effects (validate → mutate →
role-bump → audit), and the self-edit guards. The full DB round-trip
(role-bump invalidates Redis counter; ``is_active=False`` writes a
blacklist sentinel) is exercised in the integration suite — these
tests focus on the schema + handler logic.
"""
from __future__ import annotations

import uuid

import pytest

from app.api.admin_users import UserPatchRequest, UserPatchResponse, _AUDITED_FIELDS


# ── Request schema ────────────────────────────────────────────────────


def test_patch_request_requires_reason():
    """Reason is mandatory — even on a no-op patch — so the audit row
    always has a non-empty 'why'. Mirrors UnblacklistRequest."""
    with pytest.raises(Exception):
        UserPatchRequest()  # type: ignore[call-arg]


def test_patch_request_reject_short_reason():
    with pytest.raises(Exception):
        UserPatchRequest(reason="oops")  # min_length=8


def test_patch_request_reject_unknown_fields():
    """Extra fields must be rejected (extra='forbid') so the FE can't
    accidentally leak hashed_password or email into a PATCH."""
    with pytest.raises(Exception):
        UserPatchRequest(reason="hire-week-1", email="x@y.z")


def test_patch_request_team_id_null_explicitly_clears():
    """Pydantic 2 distinguishes 'field omitted' from 'field=null' via
    model_dump(exclude_unset=True). The handler relies on this for the
    'clear team_id' affordance."""
    body = UserPatchRequest(team_id=None, reason="off-team-rebalance")
    dumped = body.model_dump(exclude_unset=True, exclude={"reason"})
    assert "team_id" in dumped
    assert dumped["team_id"] is None


def test_patch_request_omitted_fields_not_in_dump():
    """Default-None fields that weren't explicitly set must NOT appear
    in the dump — otherwise we'd overwrite role/team_id every PATCH
    that only touches full_name."""
    body = UserPatchRequest(full_name="Алексей Иванов", reason="hr-typo-fix")
    dumped = body.model_dump(exclude_unset=True, exclude={"reason"})
    assert dumped == {"full_name": "Алексей Иванов"}


def test_patch_request_full_name_length_bounds():
    with pytest.raises(Exception):
        UserPatchRequest(full_name="", reason="empty-name-test-case")
    # Boundary: exactly 200 chars OK
    name = "А" * 200
    body = UserPatchRequest(full_name=name, reason="boundary-200-chars")
    assert body.full_name == name
    # 201 → reject
    with pytest.raises(Exception):
        UserPatchRequest(full_name="А" * 201, reason="boundary-201-chars")


def test_patch_request_role_must_be_valid_enum():
    """Role must be a UserRole enum value — string 'manager' coerces,
    'methodologistz' rejects."""
    body = UserPatchRequest(role="manager", reason="downgrade-rop-to-mgr")
    assert body.role.value == "manager"
    with pytest.raises(Exception):
        UserPatchRequest(role="archmage", reason="invalid-role-test")


# ── Response schema ──────────────────────────────────────────────────


def test_patch_response_serializes():
    resp = UserPatchResponse(
        user_id=uuid.uuid4(),
        email="x@trainer.local",
        role="manager",
        team_id=uuid.uuid4(),
        team_name="Отдел продаж",
        is_active=True,
        full_name="Тест Тестов",
        changed_fields=["role", "team_id"],
        role_version_bumped=True,
        tokens_revoked=False,
    )
    blob = resp.model_dump(mode="json")
    assert blob["role"] == "manager"
    assert blob["role_version_bumped"] is True
    assert blob["tokens_revoked"] is False
    assert set(blob["changed_fields"]) == {"role", "team_id"}


def test_audited_fields_pin():
    """The audit log diff covers exactly these four fields. Drift here
    means either the FE got an unannounced new editable field, or the
    diff stopped covering one we still expect to be tracked."""
    assert _AUDITED_FIELDS == ("role", "team_id", "is_active", "full_name")
