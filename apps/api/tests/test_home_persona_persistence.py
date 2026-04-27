"""Regression test for the /home → training persona drift bug.

Bug shipped to prod 2026-04-27: a manager opens /home, sees a card
"Входящий звонок: Макаров Григорий, Рязань, 1710K", clicks Ответить
→ pre-training screen shows a COMPLETELY DIFFERENT client (Васильев
Кирилл, Уфа, 1.94M).

Root cause: `apps/api/app/api/home.py:97-105` (pre-fix) created a
TrainingSession with the previewed profile in `custom_params.
waiting_client_profile`, but the WS handler at
`apps/api/app/ws/training.py:3091-3105` ignored that key and
generated a new ClientProfile from scratch. Tests below pin the
fix: `persist_client_profile_from_dict` writes the previewed
profile as a ClientProfile row keyed by session_id, so the WS
handler's `existing_profile` branch (lines 3064-3076) finds it.

These tests are PURE PYTHON — they exercise the helper directly
without touching Postgres (the helper's only DB call is
`db.add()` + `db.flush()`, which we mock). The real DB round-trip
runs on CI's pg16 service through the wider session-start tests.

The test that would FAIL on pre-fix code:
    test_persist_uses_supplied_profile_not_random
proves the symptom — the helper does NOT regenerate and uses every
field from the supplied dict. If somebody re-introduces a code path
that calls `generate_client_profile` instead, this test catches it
the moment they change the helper.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """AsyncMock DB session with add() / flush() — the helper's only ops."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def previewed_profile() -> dict:
    """Mirror of the on-prod preview cache shape — what /home shows the user
    BEFORE they click Ответить. Field set comes from
    `dataclasses.asdict(GeneratedProfile)` per
    `home_client_rotation.py:128`."""
    return {
        "full_name": "Макаров Григорий Львович",
        "age": 47,
        "gender": "male",
        "city": "Рязань",
        "archetype_code": "skeptic",
        "education": "высшее",
        "total_debt": 1_710_000,
        "creditors": [
            {"name": "Сбербанк", "amount": 1_200_000},
            {"name": "Тинькофф", "amount": 510_000},
        ],
        "income": 65_000,
        "income_type": "official",
        "property_list": [{"type": "квартира", "status": "единственная"}],
        "fears": ["потерять квартиру", "коллекторы дома"],
        "soft_spot": "семья",
        "breaking_point": "угроза детям",
        "trust_level": 4,
        "resistance_level": 6,
        "lead_source": "cold_base",
    }


# ── The regression test that proves the symptom ────────────────────────────


@pytest.mark.asyncio
async def test_persist_uses_supplied_profile_not_random(mock_db, previewed_profile):
    """The helper MUST persist EXACTLY the supplied dict's fields —
    no randomization, no fallback to a generator. This is the core
    invariant of the bug fix. If it ever fails, the persona drift
    has returned."""
    from app.services.client_generator import persist_client_profile_from_dict

    session_id = uuid.uuid4()
    profile = await persist_client_profile_from_dict(
        session_id=session_id,
        profile_dict=previewed_profile,
        db=mock_db,
    )

    # Field-for-field, the persisted row matches the preview
    assert profile.session_id == session_id
    assert profile.full_name == "Макаров Григорий Львович"  # NOT "Васильев Кирилл"
    assert profile.age == 47
    assert profile.gender == "male"
    assert profile.city == "Рязань"  # NOT "Уфа"
    assert profile.archetype_code == "skeptic"
    assert profile.total_debt == 1_710_000  # NOT 1_940_000
    assert profile.creditors == [
        {"name": "Сбербанк", "amount": 1_200_000},
        {"name": "Тинькофф", "amount": 510_000},
    ]
    assert profile.income == 65_000
    assert profile.income_type == "official"
    assert profile.property_list == [{"type": "квартира", "status": "единственная"}]
    assert profile.fears == ["потерять квартиру", "коллекторы дома"]
    assert profile.soft_spot == "семья"
    assert profile.breaking_point == "угроза детям"
    assert profile.trust_level == 4
    assert profile.resistance_level == 6
    assert profile.lead_source == "cold_base"

    # Helper actually inserted + flushed — caller doesn't have to
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()


# ── Edge cases — partial dict, defaults, type coercion ─────────────────────


@pytest.mark.asyncio
async def test_persist_with_partial_dict_uses_safe_defaults(mock_db):
    """If the cache is partial (e.g. an old format from before some
    field was added), the helper still inserts cleanly — missing
    keys fall back to sensible ClientProfile column defaults."""
    from app.services.client_generator import persist_client_profile_from_dict

    profile = await persist_client_profile_from_dict(
        session_id=uuid.uuid4(),
        profile_dict={"full_name": "Минимальный Клиент"},
        db=mock_db,
    )

    assert profile.full_name == "Минимальный Клиент"
    # Defaults from the helper signature — not magic from the model
    assert profile.age == 30
    assert profile.gender == "male"
    assert profile.city == "Москва"
    assert profile.archetype_code == "skeptic"
    assert profile.total_debt == 500_000
    assert profile.creditors == []
    assert profile.income is None
    assert profile.income_type == "official"
    assert profile.property_list == []
    assert profile.fears == []
    assert profile.soft_spot is None
    assert profile.trust_level == 5
    assert profile.lead_source == "cold_base"


@pytest.mark.asyncio
async def test_persist_coerces_numeric_strings(mock_db, previewed_profile):
    """Cache layer (Redis JSON) might re-serialize ints as strings
    in some edge cases. Helper coerces them so a stale-format cache
    doesn't 500 the start."""
    from app.services.client_generator import persist_client_profile_from_dict

    profile_dict = dict(previewed_profile)
    profile_dict["age"] = "47"  # str → must coerce to int
    profile_dict["total_debt"] = "1710000"
    profile_dict["trust_level"] = "4"

    profile = await persist_client_profile_from_dict(
        session_id=uuid.uuid4(),
        profile_dict=profile_dict,
        db=mock_db,
    )
    assert profile.age == 47
    assert profile.total_debt == 1_710_000
    assert profile.trust_level == 4


@pytest.mark.asyncio
async def test_persist_handles_null_optional_fields(mock_db):
    """`income` is nullable in the model. Helper preserves None."""
    from app.services.client_generator import persist_client_profile_from_dict

    profile = await persist_client_profile_from_dict(
        session_id=uuid.uuid4(),
        profile_dict={"full_name": "X", "income": None, "soft_spot": None},
        db=mock_db,
    )
    assert profile.income is None
    assert profile.soft_spot is None
