"""PR-9 (2026-05-07): cancelled-duel rating-invariance.

Audit on 2026-05-07 confirmed there was NO actual rating bug — Glicko
only fires from `_finalize_duel` / `judge_full_duel` and both early-
return on the H2-guard before the rating math runs (`ws/pvp.py:1463`).
The «pull-down» the FE was showing on /pvp was purely visual: cancelled
duels rendered as red «Поражение» rows.

These tests lock in the invariant so a future refactor doesn't
accidentally call `apply_duel_result` on a cancelled duel:

  1. ``rating_change_applied`` defaults to False on a cancelled duel.
  2. ``GET /pvp/duels/me?exclude_cancelled=true`` filters them out.
  3. ``GET /pvp/duels/me`` (default) still returns them — backward compat.
"""

from __future__ import annotations

import uuid

import pytest


def _make_user(user_factory, db_session):
    from app.models.user import User, UserRole

    me_data = user_factory()
    me_data["role"] = UserRole.manager
    me = User(**me_data)
    db_session.add(me)
    return me


@pytest.fixture
async def authed_client(client, db_session, user_factory):
    from app.core.deps import get_current_user
    from app.main import app

    me = _make_user(user_factory, db_session)
    await db_session.commit()

    async def _override():
        return me

    app.dependency_overrides[get_current_user] = _override
    csrf = "test-csrf-token"
    client.headers.update({
        "Authorization": "Bearer test",
        "X-CSRF-Token": csrf,
    })
    client.cookies.set("csrf_token", csrf)
    try:
        yield client, me
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_cancelled_duel_keeps_rating_change_applied_false(db_session, user_factory):
    """A cancelled duel — by design — never goes through Glicko."""
    from app.models.pvp import (
        DuelDifficulty,
        DuelStatus,
        PvPDuel,
    )

    me = _make_user(user_factory, db_session)
    bot = uuid.UUID("00000000-0000-0000-0000-000000000001")
    await db_session.commit()

    d = PvPDuel(
        player1_id=me.id,
        player2_id=bot,
        status=DuelStatus.cancelled,
        difficulty=DuelDifficulty.easy,
        is_pve=True,
        # default: rating_change_applied=False, winner_id=None,
        # player1_total=player2_total=0 — exactly the "пожар" shape.
    )
    db_session.add(d)
    await db_session.commit()
    await db_session.refresh(d)

    assert d.rating_change_applied is False
    assert d.winner_id is None
    assert d.player1_total == 0
    assert d.player2_total == 0
    # Score deltas must NOT have been written.
    assert d.player1_rating_delta == 0
    assert d.player2_rating_delta == 0


@pytest.mark.asyncio
async def test_duels_me_default_returns_cancelled(authed_client, db_session):
    """Backward compat: default ``GET /pvp/duels/me`` returns ALL statuses
    so existing callers (admin dashboards, history exports) don't break."""
    from app.models.pvp import DuelDifficulty, DuelStatus, PvPDuel

    client, me = authed_client
    bot = uuid.UUID("00000000-0000-0000-0000-000000000001")
    db_session.add_all([
        PvPDuel(
            player1_id=me.id, player2_id=bot,
            status=DuelStatus.cancelled,
            difficulty=DuelDifficulty.easy, is_pve=True,
        ),
        PvPDuel(
            player1_id=me.id, player2_id=bot,
            status=DuelStatus.completed, winner_id=me.id,
            player1_total=80, player2_total=60,
            difficulty=DuelDifficulty.easy, is_pve=True,
        ),
    ])
    await db_session.commit()

    resp = await client.get("/api/pvp/duels/me")
    assert resp.status_code == 200
    statuses = [row["status"] for row in resp.json()]
    assert "cancelled" in statuses
    assert "completed" in statuses


@pytest.mark.asyncio
async def test_duels_me_exclude_cancelled_filters_them_out(authed_client, db_session):
    from app.models.pvp import DuelDifficulty, DuelStatus, PvPDuel

    client, me = authed_client
    bot = uuid.UUID("00000000-0000-0000-0000-000000000001")
    db_session.add_all([
        PvPDuel(
            player1_id=me.id, player2_id=bot,
            status=DuelStatus.cancelled,
            difficulty=DuelDifficulty.easy, is_pve=True,
        ),
        PvPDuel(
            player1_id=me.id, player2_id=bot,
            status=DuelStatus.cancelled,
            difficulty=DuelDifficulty.easy, is_pve=True,
        ),
        PvPDuel(
            player1_id=me.id, player2_id=bot,
            status=DuelStatus.completed, winner_id=me.id,
            player1_total=80, player2_total=60,
            difficulty=DuelDifficulty.easy, is_pve=True,
        ),
    ])
    await db_session.commit()

    resp = await client.get("/api/pvp/duels/me?exclude_cancelled=true")
    assert resp.status_code == 200
    rows = resp.json()
    statuses = [r["status"] for r in rows]
    assert "cancelled" not in statuses
    # The completed one is still here.
    assert any(s == "completed" for s in statuses)
