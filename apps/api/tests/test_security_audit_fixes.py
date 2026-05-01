"""Tests for the 9-layer system audit security fixes (SEC-2026-05-02).

Locks in 4 contracts:

* CSRF middleware ALSO gates on the ``access_token`` cookie, not just
  the ``Authorization`` header. Cookie-only authed requests can no
  longer bypass CSRF.

* WS handlers ``_handle_rapid_fire`` / ``_handle_gauntlet`` /
  ``_handle_team_battle`` reject callers that don't own the resource.
  Previously any user with a leaked id could attach to someone else's
  session.

* ``_handle_duel_ready`` resets its correlation_id contextvar on exit
  so the next event in the receive-loop doesn't inherit a stale
  duel_id in its log lines.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── CSRF cookie bypass close (main.py) ─────────────────────────────────────


def test_csrf_has_auth_includes_cookie_check():
    """The CSRF gate must consider both the Authorization header AND the
    access_token cookie. Audit found that cookie-only authed requests
    bypassed CSRF entirely.
    """
    import inspect
    from app.main import CSRFMiddleware

    src = inspect.getsource(CSRFMiddleware.dispatch)
    assert 'request.cookies.get("access_token")' in src, (
        "CSRF gate must check access_token cookie (SEC-2026-05-02)"
    )


# ── WS hijack ownership checks ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_rapid_fire_rejects_non_owner():
    """A user who does not own a RapidFireMatch must be rejected."""
    from app.ws import pvp as pvp_ws

    owner = uuid.uuid4()
    intruder = uuid.uuid4()
    match_id = uuid.uuid4()

    fake_match = MagicMock(player1_id=owner, player2_id=None, id=match_id)
    sel_result = MagicMock()
    sel_result.scalar_one_or_none = MagicMock(return_value=fake_match)
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=sel_result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_db)
    cm.__aexit__ = AsyncMock(return_value=False)
    fake_ws = AsyncMock()

    with patch("app.ws.pvp.async_session", return_value=cm), \
         patch("app.ws.pvp._send", new=AsyncMock()) as mock_send:
        await pvp_ws._handle_rapid_fire(fake_ws, intruder, match_id)

    error_calls = [c for c in mock_send.call_args_list if c.args[1] == "error"]
    assert error_calls, "expected error event on hijack attempt"
    detail = error_calls[0].args[2].get("detail", "")
    assert "запрещ" in detail.lower() or "доступ" in detail.lower(), (
        f"expected access-denied error, got {detail!r}"
    )


@pytest.mark.asyncio
async def test_handle_gauntlet_rejects_non_owner():
    from app.ws import pvp as pvp_ws

    owner = uuid.uuid4()
    intruder = uuid.uuid4()
    run_id = uuid.uuid4()

    fake_run = MagicMock(user_id=owner, id=run_id)
    sel_result = MagicMock()
    sel_result.scalar_one_or_none = MagicMock(return_value=fake_run)
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=sel_result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_db)
    cm.__aexit__ = AsyncMock(return_value=False)
    fake_ws = AsyncMock()

    with patch("app.ws.pvp.async_session", return_value=cm), \
         patch("app.ws.pvp._send", new=AsyncMock()) as mock_send:
        await pvp_ws._handle_gauntlet(fake_ws, intruder, run_id)

    error_calls = [c for c in mock_send.call_args_list if c.args[1] == "error"]
    assert error_calls
    detail = error_calls[0].args[2].get("detail", "").lower()
    assert "запрещ" in detail or "доступ" in detail


@pytest.mark.asyncio
async def test_handle_team_battle_rejects_non_member():
    from app.ws import pvp as pvp_ws

    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    outsider = uuid.uuid4()
    team_id = uuid.uuid4()

    fake_team = MagicMock(player1_id=p1, player2_id=p2, id=team_id)
    sel_result = MagicMock()
    sel_result.scalar_one_or_none = MagicMock(return_value=fake_team)
    fake_db = MagicMock()
    fake_db.execute = AsyncMock(return_value=sel_result)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_db)
    cm.__aexit__ = AsyncMock(return_value=False)
    fake_ws = AsyncMock()

    with patch("app.ws.pvp.async_session", return_value=cm), \
         patch("app.ws.pvp._send", new=AsyncMock()) as mock_send:
        await pvp_ws._handle_team_battle(fake_ws, outsider, team_id)

    error_calls = [c for c in mock_send.call_args_list if c.args[1] == "error"]
    assert error_calls
    detail = error_calls[0].args[2].get("detail", "").lower()
    assert "команд" in detail


def test_ownership_check_inline_for_legitimate_member():
    """Sanity (static, not async): the ownership check expression in
    _handle_team_battle treats player1_id and player2_id as both
    legitimate, rejects only the third-party. This catches any future
    accidental "==" / "!=" inversion via source inspection.
    """
    import inspect
    from app.ws import pvp as pvp_ws

    src = inspect.getsource(pvp_ws._handle_team_battle)
    # Expect the SEC-2026-05-02 ownership guard to use AND between two
    # !=, so EITHER player1_id OR player2_id passes. Reject inverted
    # logic that would have used OR (which would lock out the team).
    assert "user_id != team.player1_id and user_id != team.player2_id" in src, (
        "team-battle ownership guard must use AND between the two != "
        "comparisons (SEC-2026-05-02)"
    )


# ── Correlation reset on _handle_duel_ready exit ───────────────────────────


@pytest.mark.asyncio
async def test_handle_duel_ready_resets_correlation_id_on_exit():
    """After the handler returns, the contextvar must be back to its
    pre-call value (the sentinel set by the test)."""
    from app.core.correlation import (
        bind_correlation_id,
        get_correlation_id,
        reset_correlation_id,
    )
    from app.ws import pvp as pvp_ws

    sentinel_token = bind_correlation_id("sentinel-pre-handler")
    try:
        with patch("app.ws.pvp._load_duel_context", new=AsyncMock(return_value=None)), \
             patch("app.ws.pvp._send_to_user", new=AsyncMock()):
            await pvp_ws._handle_duel_ready(uuid.uuid4(), uuid.uuid4())
        # After handler — back to sentinel, NOT the duel id.
        assert get_correlation_id() == "sentinel-pre-handler"
    finally:
        reset_correlation_id(sentinel_token)
