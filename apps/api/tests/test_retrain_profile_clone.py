"""Bug fix 2026-04-29 — retrain ("Повторить звонок") must keep the same person.

Pre-fix: clicking «Повторить звонок» on /results created a new session that
copied scenario/archetype/profession from the source session, but the WS
handler ran ``generate_client_profile`` from scratch — so the manager saw
the OLD name on the /results card and a DIFFERENT name (and different debt
amounts, fears, soft_spot, traps, objection chain) inside the actual call.

Fix: ``_clone_source_session_profile`` clones the source's ClientProfile
identity-for-identity onto the new session, mirroring the multi-call story
flow. This test pins the contract.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ws.training import _clone_source_session_profile


class _FakeProfile:
    """Drop-in for ClientProfile ORM rows in this unit test."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _make_source_profile(session_id: uuid.UUID) -> _FakeProfile:
    return _FakeProfile(
        session_id=session_id,
        full_name="Иван Петрович Крылов",
        age=42,
        gender="male",
        city="Саратов",
        archetype_code="skeptic",
        profession_id=uuid.uuid4(),
        education_level="higher",
        legal_literacy="medium",
        total_debt=1_200_000,
        creditors=["Сбер", "Тинькофф"],
        income=85_000,
        income_type="salary",
        property_list=[],
        fears=["потерять квартиру"],
        soft_spot="дочь-школьница",
        trust_level=0.3,
        resistance_level=0.6,
        lead_source="cold_base",
        call_history=[],
        crm_notes="разговаривал в марте, обещал перезвонить",
        hidden_objections=["боится мошенников"],
        trap_ids=[uuid.uuid4(), uuid.uuid4()],
        chain_id=uuid.uuid4(),
        cascade_ids=[],
        breaking_point=0.8,
    )


def _build_db_returning(profile: _FakeProfile | None) -> MagicMock:
    """Build a fake AsyncSession whose .execute returns the given profile."""
    db = MagicMock()
    scalar_one = MagicMock(return_value=profile)
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = scalar_one
    db.execute = AsyncMock(return_value=exec_result)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_clone_carries_full_identity_to_new_session():
    """Every identity-defining field must transfer."""
    src_id = uuid.uuid4()
    new_id = uuid.uuid4()
    src = _make_source_profile(src_id)
    db = _build_db_returning(src)

    cloned = await _clone_source_session_profile(src_id, new_id, db)
    assert cloned is not None, "must return the cloned profile"
    assert cloned.session_id == new_id, "session_id must be the NEW id, not the source"

    # Every identity-defining field must match — these are what the user sees.
    for field in (
        "full_name", "age", "gender", "city", "archetype_code",
        "profession_id", "education_level", "legal_literacy",
        "total_debt", "creditors", "income", "income_type",
        "property_list", "fears", "soft_spot",
        "trust_level", "resistance_level", "lead_source",
        "call_history", "crm_notes", "hidden_objections",
        "trap_ids", "chain_id", "cascade_ids", "breaking_point",
    ):
        assert getattr(cloned, field) == getattr(src, field), (
            f"field {field!r} must clone verbatim — name/debt/traps are what "
            f"the manager recognises across retrains"
        )

    db.add.assert_called_once_with(cloned)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_clone_returns_none_when_source_profile_missing():
    """Legacy / unfinished sessions have no ClientProfile — fall through."""
    src_id = uuid.uuid4()
    new_id = uuid.uuid4()
    db = _build_db_returning(None)
    cloned = await _clone_source_session_profile(src_id, new_id, db)
    assert cloned is None
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_clone_does_not_mutate_source_profile():
    """The source row must be left intact — only a NEW row is added."""
    src_id = uuid.uuid4()
    new_id = uuid.uuid4()
    src = _make_source_profile(src_id)
    db = _build_db_returning(src)
    await _clone_source_session_profile(src_id, new_id, db)
    # Source still points at the source session id.
    assert src.session_id == src_id, "source profile.session_id must not be touched"
    assert src.full_name == "Иван Петрович Крылов"


@pytest.mark.asyncio
async def test_clone_preserves_traps_and_chain_ids():
    """Traps and objection chain are part of "this person" — must transfer."""
    src_id = uuid.uuid4()
    new_id = uuid.uuid4()
    src = _make_source_profile(src_id)
    expected_traps = list(src.trap_ids)
    expected_chain = src.chain_id
    db = _build_db_returning(src)
    cloned = await _clone_source_session_profile(src_id, new_id, db)
    assert cloned is not None
    assert cloned.trap_ids == expected_traps
    assert cloned.chain_id == expected_chain
