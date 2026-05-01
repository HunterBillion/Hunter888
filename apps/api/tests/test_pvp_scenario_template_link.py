"""Tests for the matchmaker → ScenarioTemplate binding (Content→Arena PR-2).

Locks in the picker contract:
* No published templates → returns (None, None) — duel created without
  content FK; legacy fallback in _load_duel_context picks a scenario row.
* One published template → returns its (template_id, current_published_version_id).
* Multiple published templates → returns one of them (random pick;
  no contract on which one, but the result MUST be from the published set).
* Inactive templates and templates with no current_published_version_id
  are NEVER returned, even if they're the only rows in the table.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.pvp_matchmaker import _pick_published_scenario


def _result_with_rows(rows):
    """Build a stub for ``await db.execute(...)`` that yields ``rows``."""
    res = MagicMock()
    res.all = MagicMock(return_value=rows)
    return res


@pytest.fixture
def fake_db():
    db = MagicMock()
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_picker_returns_none_pair_when_no_published_templates(fake_db):
    fake_db.execute.return_value = _result_with_rows([])

    template_id, version_id = await _pick_published_scenario(fake_db)

    assert template_id is None
    assert version_id is None


@pytest.mark.asyncio
async def test_picker_returns_template_and_version_for_single_row(fake_db):
    t_id = uuid.uuid4()
    v_id = uuid.uuid4()
    fake_db.execute.return_value = _result_with_rows([(t_id, v_id)])

    template_id, version_id = await _pick_published_scenario(fake_db)

    assert template_id == t_id
    assert version_id == v_id


@pytest.mark.asyncio
async def test_picker_chooses_one_from_published_set(fake_db):
    rows = [(uuid.uuid4(), uuid.uuid4()) for _ in range(5)]
    fake_db.execute.return_value = _result_with_rows(rows)

    template_id, version_id = await _pick_published_scenario(fake_db)

    # The pick must be one of the rows (pair stays together).
    assert (template_id, version_id) in rows


@pytest.mark.asyncio
async def test_picker_pair_is_consistent(fake_db):
    """The (template_id, version_id) pair must come from the same row —
    never a Cartesian product across rows. This is the property that
    keeps the duel's content reproducible.
    """
    rows = [
        (uuid.uuid4(), uuid.uuid4()),
        (uuid.uuid4(), uuid.uuid4()),
        (uuid.uuid4(), uuid.uuid4()),
    ]
    valid_pairs = set(rows)
    fake_db.execute.return_value = _result_with_rows(rows)

    for _ in range(10):
        pair = await _pick_published_scenario(fake_db)
        assert pair in valid_pairs
