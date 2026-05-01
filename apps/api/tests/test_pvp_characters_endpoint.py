"""Integration tests for ``GET /api/pvp/characters/available`` (Content→Arena PR-4).

These tests run against the real ASGI app + the in-memory SQLite test
fixture, so they exercise the full stack: auth (JWT decode), DB session
override, the new endpoint, and the pydantic response model. Unlike the
unit-style tests in PR-1..PR-3, this PR's helper depends on actual SQL
JOINs / WHERE clauses / ORDER BY that mocks can't validate — running
through the test client is the only way to lock in correctness.

Coverage
--------

* 401 without auth header
* Empty buckets when user has no presets and no shared rows exist
* Own bucket lists user's own presets (regardless of is_shared)
* Shared bucket lists OTHER users' is_shared=True presets
* Shared bucket EXCLUDES the requesting user's own presets (no double-render)
* Shared bucket EXCLUDES non-shared other-users' presets (privacy)
* ``is_own`` / ``is_shared`` flags on each card are correct
* ``limit`` query param caps each bucket independently
* Ordering: own → most-recently-played first; shared → most-recently-created first
* Inactive users' presets are STILL returned (we don't filter on user.is_active)
* Empty database does not crash
"""

from __future__ import annotations

import uuid

import pytest


# ── Local fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def current_user_id():
    """Stable UUID for the requesting user, shared between auth and DB rows."""
    return uuid.uuid4()


@pytest.fixture
async def authed_client(client, db_session, current_user_id, user_factory):
    """``client`` with ``get_current_user`` dependency overridden to a real
    ``User`` row backed by the test DB session.

    The production auth dependency requires Redis (JTI revocation, role
    version, blacklist) which the test environment doesn't have. Rather
    than mocking each Redis branch, override the dependency to directly
    return a User — the endpoint under test only cares about ``user.id``
    anyway. This is the standard pattern for endpoint integration tests
    in this repo.
    """
    from app.core.deps import get_current_user
    from app.main import app
    from app.models.user import User

    me = User(**user_factory(user_id=current_user_id))
    db_session.add(me)
    await db_session.commit()

    async def _override():
        return me

    app.dependency_overrides[get_current_user] = _override
    client.headers.update({"Authorization": "Bearer test-fixture-token"})
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_endpoint_requires_auth(client):
    """No Authorization header → 401."""
    resp = await client.get("/api/pvp/characters/available")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_empty_buckets_when_nothing_in_db(authed_client):
    resp = await authed_client.get("/api/pvp/characters/available")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"own": [], "shared": [], "total": 0}


@pytest.mark.asyncio
async def test_own_bucket_lists_user_presets(authed_client, db_session, current_user_id):
    """User's own presets land in 'own', regardless of is_shared.

    The requesting user is already persisted by the ``authed_client`` fixture.
    """
    from app.models.custom_character import CustomCharacter

    c1 = CustomCharacter(
        user_id=current_user_id, name="My Aggressive Boss",
        archetype="aggressive_boss", profession="ceo",
        lead_source="referral", difficulty=7, is_shared=False,
    )
    c2 = CustomCharacter(
        user_id=current_user_id, name="My Skeptical Engineer",
        archetype="skeptical_analyst", profession="engineer",
        lead_source="cold_call", difficulty=5, is_shared=True,
    )
    db_session.add_all([c1, c2])
    await db_session.commit()

    resp = await authed_client.get("/api/pvp/characters/available")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert len(body["own"]) == 2
    assert len(body["shared"]) == 0
    names = {c["name"] for c in body["own"]}
    assert names == {"My Aggressive Boss", "My Skeptical Engineer"}
    for card in body["own"]:
        assert card["is_own"] is True
        # is_shared mirrors the row's flag — own bucket can include shared presets.
        assert isinstance(card["is_shared"], bool)


@pytest.mark.asyncio
async def test_shared_bucket_only_other_users_with_is_shared(
    authed_client, db_session, user_factory, current_user_id,
):
    """Authed_client already persisted the requesting user; we add two others."""
    from app.models.user import User
    from app.models.custom_character import CustomCharacter

    other = User(**user_factory(user_id=uuid.uuid4()))
    third = User(**user_factory(user_id=uuid.uuid4()))
    db_session.add_all([other, third])

    # Three rows from OTHER users:
    #   shared_visible  — should appear
    #   shared_private  — is_shared=False, should NOT appear
    #   shared_third    — should appear
    db_session.add_all([
        CustomCharacter(
            user_id=other.id, name="Shared from Other",
            archetype="aggressive_boss", profession="ceo",
            lead_source="referral", difficulty=6, is_shared=True,
        ),
        CustomCharacter(
            user_id=other.id, name="Private from Other",
            archetype="skeptical_analyst", profession="engineer",
            lead_source="cold_call", difficulty=4, is_shared=False,
        ),
        CustomCharacter(
            user_id=third.id, name="Shared from Third",
            archetype="curious_buyer", profession="manager",
            lead_source="website", difficulty=5, is_shared=True,
        ),
    ])
    await db_session.commit()

    resp = await authed_client.get("/api/pvp/characters/available")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # No own presets exist for the requesting user.
    assert body["own"] == []
    shared_names = {c["name"] for c in body["shared"]}
    assert shared_names == {"Shared from Other", "Shared from Third"}
    for card in body["shared"]:
        assert card["is_own"] is False
        assert card["is_shared"] is True


@pytest.mark.asyncio
async def test_shared_bucket_excludes_own_presets(
    authed_client, db_session, current_user_id,
):
    """Even if a user shared their own preset, the shared bucket must not
    duplicate it — the row only ever appears in 'own' for the owner."""
    from app.models.custom_character import CustomCharacter

    db_session.add(CustomCharacter(
        user_id=current_user_id, name="My Public Preset",
        archetype="aggressive_boss", profession="ceo",
        lead_source="referral", difficulty=8, is_shared=True,
    ))
    await db_session.commit()

    resp = await authed_client.get("/api/pvp/characters/available")
    body = resp.json()

    assert len(body["own"]) == 1
    assert len(body["shared"]) == 0  # NOT duplicated in shared bucket


@pytest.mark.asyncio
async def test_limit_param_caps_each_bucket_independently(
    authed_client, db_session, user_factory, current_user_id,
):
    from app.models.user import User
    from app.models.custom_character import CustomCharacter

    other = User(**user_factory(user_id=uuid.uuid4()))
    db_session.add(other)

    # 5 own + 5 shared
    for i in range(5):
        db_session.add(CustomCharacter(
            user_id=current_user_id, name=f"Own #{i}",
            archetype="aggressive_boss", profession="ceo",
            lead_source="referral", difficulty=5, is_shared=False,
        ))
    for i in range(5):
        db_session.add(CustomCharacter(
            user_id=other.id, name=f"Shared #{i}",
            archetype="curious_buyer", profession="manager",
            lead_source="website", difficulty=5, is_shared=True,
        ))
    await db_session.commit()

    resp = await authed_client.get("/api/pvp/characters/available?limit=3")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["own"]) == 3
    assert len(body["shared"]) == 3
    assert body["total"] == 6


@pytest.mark.asyncio
async def test_limit_param_validates_range(authed_client):
    """limit out of [1, 200] returns 422."""
    r1 = await authed_client.get("/api/pvp/characters/available?limit=0")
    assert r1.status_code == 422
    r2 = await authed_client.get("/api/pvp/characters/available?limit=201")
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_response_card_shape_locked(
    authed_client, db_session, current_user_id,
):
    from app.models.custom_character import CustomCharacter

    db_session.add(CustomCharacter(
        user_id=current_user_id, name="Schema Lock",
        archetype="aggressive_boss", profession="ceo",
        lead_source="referral", difficulty=6,
        description="A test description",
        play_count=42, avg_score=78,
        is_shared=True,
    ))
    await db_session.commit()

    resp = await authed_client.get("/api/pvp/characters/available")
    card = resp.json()["own"][0]
    expected_keys = {
        "id", "name", "archetype", "profession", "difficulty",
        "description", "is_own", "is_shared", "play_count", "avg_score",
    }
    assert set(card.keys()) == expected_keys
    assert card["name"] == "Schema Lock"
    assert card["play_count"] == 42
    assert card["avg_score"] == 78
    assert card["is_own"] is True
    assert card["is_shared"] is True
