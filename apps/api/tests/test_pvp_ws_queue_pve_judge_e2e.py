from __future__ import annotations

import uuid
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.pvp import DuelDifficulty, DuelStatus
from app.services.pvp_judge import JudgeRoundScore


class _AsyncSessionCM:
    def __init__(self):
        self.db = AsyncMock()
        self.db.commit = AsyncMock()
        self.db.execute = AsyncMock()
        self.db.add = AsyncMock()
        self.db.flush = AsyncMock()

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_ws_queue_to_pve_fallback_then_round_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Covers chain: queue -> pve fallback -> duel ready -> round -> judge.score.

    This is intentionally WS-handler e2e (not pure unit): we execute real
    matchmaking fallback and duel-message flow, with only external IO mocked.
    """
    from app.ws import pvp as pvp_ws

    user_id = uuid.uuid4()
    duel_id = uuid.uuid4()

    duel = SimpleNamespace(
        id=duel_id,
        player1_id=user_id,
        player2_id=pvp_ws.BOT_ID,
        status=DuelStatus.pending,
        difficulty=DuelDifficulty.easy,
        is_pve=True,
        pve_metadata={},
        pve_mode="standard",
        scenario_template_id=None,
        scenario_version_id=None,
    )

    events: list[tuple[uuid.UUID, str, dict]] = []

    async def _send_to_user(uid: uuid.UUID, msg_type: str, data: dict | None = None) -> None:
        events.append((uid, msg_type, dict(data or {})))

    async def _player_card(_db, uid: uuid.UUID) -> dict:
        if uid == pvp_ws.BOT_ID:
            return {"id": str(uid), "name": "AI Бот", "tier": "ai", "avatar_url": None}
        return {"id": str(uid), "name": "Learner", "tier": "silver", "avatar_url": None}

    async def _start_round_stub(duel_uuid: uuid.UUID, round_number: int) -> None:
        async with pvp_ws._duel_sessions_lock:
            session = pvp_ws._duel_sessions.get(duel_uuid)
            if not session or session.get("completed"):
                return
            session["round"] = round_number
            session["round_started_at"] = time.time()

    seller_score = JudgeRoundScore(
        selling_score=34,
        acting_score=0,
        legal_accuracy=12,
        flags=[],
        legal_details=[{"claim": "ст. 213.3", "accuracy": "correct_cited", "explanation": "ok"}],
        coaching_tip="Подсвети порог и срок просрочки сразу.",
        ideal_reply="При долге от 500 000 руб. и просрочке 3+ месяцев можно подать заявление.",
        key_articles=["ст. 213.3"],
        degraded=False,
        degraded_reason="",
    )
    seller_score.total = 46
    client_score = JudgeRoundScore(acting_score=19, degraded=False, degraded_reason="")
    client_score.total = 19

    # Isolate global runtime maps for this test.
    pvp_ws._duel_sessions.clear()
    pvp_ws._duel_messages.clear()
    pvp_ws._matchmaking_tasks.clear()
    pvp_ws._disconnect_tasks.clear()

    monkeypatch.setattr(pvp_ws, "async_session", lambda: _AsyncSessionCM())
    monkeypatch.setattr(pvp_ws, "_send_to_user", _send_to_user)
    monkeypatch.setattr(pvp_ws, "_player_card", _player_card)
    monkeypatch.setattr(pvp_ws, "_update_duel_row", AsyncMock())
    monkeypatch.setattr(pvp_ws, "_generate_ai_reply", AsyncMock(return_value="AI: уточните детали"))
    monkeypatch.setattr(pvp_ws, "judge_round", AsyncMock(return_value=(seller_score, client_score)))
    monkeypatch.setattr(pvp_ws, "_start_round", _start_round_stub)

    monkeypatch.setattr(pvp_ws, "ac_init_player", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        pvp_ws,
        "ac_check_message",
        lambda *_args, **_kwargs: SimpleNamespace(should_warn=False, flags=[]),
    )

    monkeypatch.setattr(pvp_ws, "_load_duel_context", AsyncMock(return_value={
        "duel": duel,
        "player1_name": "Learner",
        "player2_name": "AI Бот",
        "scenario_title": "PvE Fallback Scenario",
    }))

    monkeypatch.setattr(pvp_ws.PvPDuelRedis, "save_session", AsyncMock())
    monkeypatch.setattr(pvp_ws.PvPDuelRedis, "save_messages", AsyncMock())
    monkeypatch.setattr(pvp_ws.PvPDuelRedis, "delete_session", AsyncMock())
    monkeypatch.setattr(pvp_ws.PvPDuelRedis, "get_duel_for_user", AsyncMock(return_value=None))

    monkeypatch.setattr(pvp_ws.matchmaker, "is_in_queue", AsyncMock(return_value=True))
    monkeypatch.setattr(pvp_ws.matchmaker, "find_match", AsyncMock(return_value=None))
    monkeypatch.setattr(pvp_ws.matchmaker, "get_queue_size", AsyncMock(return_value=1))
    monkeypatch.setattr(pvp_ws.matchmaker, "create_pve_duel", AsyncMock(return_value=duel))
    monkeypatch.setattr(pvp_ws.matchmaker, "leave_queue", AsyncMock(return_value=True))

    monkeypatch.setattr(pvp_ws.matchmaker, "PVE_FALLBACK_TIMEOUT_EMPTY_QUEUE", 0)
    monkeypatch.setattr(pvp_ws.matchmaker, "PVE_FALLBACK_QUEUE_SIZE_THRESHOLD", 2)

    await pvp_ws._background_matchmaking(user_id)

    match_events = [event for event in events if event[1] == "match.found"]
    assert match_events, "expected match.found after queue fallback"
    match_payload = match_events[-1][2]
    assert match_payload["is_pve"] is True
    assert match_payload["duel_id"] == str(duel_id)

    await pvp_ws._handle_duel_ready(user_id, duel_id)

    for idx in range(4):
        await pvp_ws._handle_duel_message(user_id, f"user-msg-{idx}")

    judge_events = [event for event in events if event[1] == "judge.score"]
    assert judge_events, "expected judge.score after round message limit"

    judge_payload = judge_events[-1][2]
    assert judge_payload["round"] == 1
    assert judge_payload["selling_score"] == 34
    assert judge_payload["legal_accuracy"] == 12
    assert judge_payload["coaching"]["tip"] == "Подсвети порог и срок просрочки сразу."

    judge_mock = pvp_ws.judge_round
    assert isinstance(judge_mock, AsyncMock)
    assert judge_mock.await_count == 1
    judge_call = judge_mock.await_args.kwargs
    assert judge_call["round_number"] == 1
    assert len(judge_call["dialog"]) == 8  # 4 user + 4 AI messages
