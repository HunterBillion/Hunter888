"""Integration tests for ``POST /api/clients/from-session/{session_id}``.

BUG NEW-4 fix: previously the FE button "Сохранить в CRM" sent only 4
fields (full_name, source, status, notes) and produced shallow cards
labelled "Клиент из тренировки, 47 лет" with no debt / creditors / story.
The new endpoint reads the session's ``ClientProfile`` row and the
``TrainingSession`` itself, then builds a populated ``RealClient``.

Coverage
--------
* Happy path: ClientProfile present → returned client has populated
  full_name, debt_amount, debt_details (creditors_list, income, etc.),
  notes summary, metadata_["source_session_id"], status by score.
* Idempotency: second call for the same session returns the SAME
  client_id (no duplicate row, 200 instead of 201).
* 404: session belongs to another user.
* 422: session has no ClientProfile row → cannot build a useful card.
* Session ↔ client link: after creation, ``TrainingSession.real_client_id``
  points at the new client (so future re-opens auto-bind).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


# ── Local fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def current_user_id():
    return uuid.uuid4()


@pytest.fixture
async def authed_client(client, db_session, current_user_id, user_factory):
    """``client`` with ``get_current_user`` overridden to a persisted User."""
    from app.core.deps import get_current_user
    from app.main import app
    from app.models.user import User

    from app.models.user import UserRole

    me_data = user_factory(user_id=current_user_id)
    # User model has Enum column; in-memory SQLite skips the coercion done
    # by Postgres on flush, so we pass the enum value explicitly.
    me_data["role"] = UserRole.manager
    me = User(**me_data)
    db_session.add(me)
    await db_session.commit()

    async def _override():
        return me

    app.dependency_overrides[get_current_user] = _override
    # CSRF middleware (main.py:457) requires X-CSRF-Token == csrf_token cookie
    # for state-changing requests. Set both to the same value to satisfy it.
    csrf = "test-csrf-token"
    client.headers.update({
        "Authorization": "Bearer test-fixture-token",
        "X-CSRF-Token": csrf,
    })
    client.cookies.set("csrf_token", csrf)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _make_scenario(db_session) -> uuid.UUID:
    """Insert a minimal Scenario row and return its id (FK requirement)."""
    from app.models.scenario import Scenario, ScenarioType

    sc = Scenario(
        id=uuid.uuid4(),
        title="Test scenario",
        description="-",
        scenario_type=ScenarioType.cold_call,
        difficulty=5,
        estimated_duration_minutes=10,
        is_active=True,
    )
    db_session.add(sc)
    await db_session.commit()
    return sc.id


async def _make_session(
    db_session,
    *,
    user_id: uuid.UUID,
    scenario_id: uuid.UUID,
    score_total: float | None = 75.0,
    started_at: datetime | None = None,
):
    from app.models.training import SessionStatus, TrainingSession

    ts = TrainingSession(
        id=uuid.uuid4(),
        user_id=user_id,
        scenario_id=scenario_id,
        status=SessionStatus.completed,
        started_at=started_at or datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        score_total=score_total,
    )
    db_session.add(ts)
    await db_session.commit()
    return ts


async def _make_profile(
    db_session,
    *,
    session_id: uuid.UUID,
    full_name: str = "Анна Дмитриевна Козлова",
    age: int = 47,
    total_debt: int = 1_400_000,
    creditors: list | None = None,
    income: int | None = 65_000,
    archetype_code: str = "skeptic",
    breaking_point: str | None = "Боится потерять единственное жильё, но магазин обещает реструктуризацию",
):
    from app.models.roleplay import ClientProfile

    profile = ClientProfile(
        id=uuid.uuid4(),
        session_id=session_id,
        full_name=full_name,
        age=age,
        gender="female",
        city="Самара",
        archetype_code=archetype_code,
        education_level="высшее",
        total_debt=total_debt,
        creditors=creditors or [
            {"name": "Сбербанк", "amount": 800_000},
            {"name": "Альфа-Банк", "amount": 600_000},
        ],
        income=income,
        income_type="official",
        property_list=[],
        fears=["потерять квартиру", "осуждение родственников"],
        soft_spot="дочь",
        breaking_point=breaking_point,
        trust_level=4,
        resistance_level=6,
        lead_source="cold_base",
    )
    db_session.add(profile)
    await db_session.commit()
    return profile


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_populates_real_client_from_profile(
    authed_client, db_session, current_user_id,
):
    """ClientProfile present → returned card has debt + creditors + meta."""
    scenario_id = await _make_scenario(db_session)
    session = await _make_session(
        db_session, user_id=current_user_id, scenario_id=scenario_id, score_total=82.0,
    )
    await _make_profile(db_session, session_id=session.id)

    resp = await authed_client.post(
        f"/api/clients/from-session/{session.id}",
        json={},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Real data, not "Клиент из тренировки, 47 лет"
    assert body["full_name"] == "Анна Дмитриевна Козлова"
    assert body["source"] == "training"
    # score 82 ≥ 70 → contacted
    assert body["status"] == "contacted"
    # Decimal serialises as string in pydantic; accept both
    assert float(body["debt_amount"]) == 1_400_000.0

    debt_details = body["debt_details"]
    assert debt_details is not None
    creditors = debt_details["creditors_list"]
    assert len(creditors) == 2
    assert {c["name"] for c in creditors} == {"Сбербанк", "Альфа-Банк"}
    assert debt_details["archetype_code"] == "skeptic"
    assert debt_details["city"] == "Самара"
    assert debt_details["income"] == 65_000

    # Notes contain the auto-summary (date + score + archetype)
    assert "Тренировка" in body["notes"]
    assert "82/100" in body["notes"]
    assert "skeptic" in body["notes"]

    # Session got linked back
    from app.models.training import TrainingSession
    from sqlalchemy import select

    refreshed = (await db_session.execute(
        select(TrainingSession).where(TrainingSession.id == session.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert str(refreshed.real_client_id) == body["id"]


@pytest.mark.asyncio
async def test_idempotent_returns_same_client_on_repeat(
    authed_client, db_session, current_user_id,
):
    """Calling twice for the same session returns the same client_id (200)."""
    scenario_id = await _make_scenario(db_session)
    session = await _make_session(
        db_session, user_id=current_user_id, scenario_id=scenario_id,
    )
    await _make_profile(db_session, session_id=session.id)

    first = await authed_client.post(f"/api/clients/from-session/{session.id}", json={})
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]

    second = await authed_client.post(f"/api/clients/from-session/{session.id}", json={})
    # 200 (already exists), not 201 (newly created), and the same row.
    assert second.status_code == 200, second.text
    assert second.json()["id"] == first_id

    # Verify no duplicate row in DB.
    from sqlalchemy import func, select
    from app.models.client import RealClient

    count = (await db_session.execute(
        select(func.count())
        .select_from(RealClient)
        .where(RealClient.manager_id == current_user_id)
    )).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_session_owned_by_other_user_returns_404(
    authed_client, db_session, current_user_id, user_factory,
):
    """Session belongs to another user → 404 (no info leak)."""
    from app.models.user import User

    other = User(**user_factory(user_id=uuid.uuid4()))
    db_session.add(other)
    await db_session.commit()

    scenario_id = await _make_scenario(db_session)
    foreign_session = await _make_session(
        db_session, user_id=other.id, scenario_id=scenario_id,
    )
    # Even if a profile exists, 404 wins on ownership check.
    await _make_profile(db_session, session_id=foreign_session.id)

    resp = await authed_client.post(
        f"/api/clients/from-session/{foreign_session.id}",
        json={},
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_session_without_client_profile_returns_422(
    authed_client, db_session, current_user_id,
):
    """No ClientProfile row → 422 (nothing to copy into CRM)."""
    scenario_id = await _make_scenario(db_session)
    session = await _make_session(
        db_session, user_id=current_user_id, scenario_id=scenario_id,
    )
    # Deliberately skip _make_profile.

    resp = await authed_client.post(
        f"/api/clients/from-session/{session.id}",
        json={},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_low_score_assigns_new_status(
    authed_client, db_session, current_user_id,
):
    """score_total < 70 → ``new`` (not ``contacted``)."""
    scenario_id = await _make_scenario(db_session)
    session = await _make_session(
        db_session, user_id=current_user_id, scenario_id=scenario_id, score_total=42.0,
    )
    await _make_profile(db_session, session_id=session.id)

    resp = await authed_client.post(f"/api/clients/from-session/{session.id}", json={})
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "new"


@pytest.mark.asyncio
async def test_full_name_strips_trailing_age_suffix(
    authed_client, db_session, current_user_id,
):
    """Some legacy display labels suffix ", 47" — bridge must strip it."""
    scenario_id = await _make_scenario(db_session)
    session = await _make_session(
        db_session, user_id=current_user_id, scenario_id=scenario_id,
    )
    await _make_profile(
        db_session, session_id=session.id,
        full_name="Сергей Петрович, 47",
    )

    resp = await authed_client.post(f"/api/clients/from-session/{session.id}", json={})
    assert resp.status_code == 201, resp.text
    assert resp.json()["full_name"] == "Сергей Петрович"
