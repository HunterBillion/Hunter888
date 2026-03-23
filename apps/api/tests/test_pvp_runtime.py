import uuid

from app.services.anti_cheat import AntiCheatAction, AntiCheatCheckType, AntiCheatSignal
from app.ws.pvp import (
    _collect_anti_cheat_flag,
    _duel_messages,
    _flatten_duel_messages,
    _match_found_payload,
)


def test_collect_anti_cheat_flag_uses_aggregated_result_contract():
    user_id = uuid.uuid4()

    class StubResult:
        max_score = 0.73
        recommended_action = AntiCheatAction.rating_freeze
        flagged_signals = [
            AntiCheatSignal(
                check_type=AntiCheatCheckType.behavioral,
                score=0.73,
                flagged=True,
                details={"reason": "template_pattern"},
            )
        ]

    payload = _collect_anti_cheat_flag(user_id, StubResult())

    assert payload["player_id"] == str(user_id)
    assert payload["score"] == 0.73
    assert payload["action"] == "rating_freeze"
    assert payload["signals"][0]["check_type"] == "behavioral"


def test_flatten_duel_messages_keeps_round_order():
    duel_id = uuid.uuid4()
    _duel_messages[duel_id] = {
        1: [{"role": "seller", "text": "r1", "round": 1, "timestamp": 1.0}],
        2: [{"role": "client", "text": "r2", "round": 2, "timestamp": 2.0}],
    }

    try:
        messages = _flatten_duel_messages(duel_id)
    finally:
        _duel_messages.pop(duel_id, None)

    assert [message["round"] for message in messages] == [1, 2]
    assert [message["text"] for message in messages] == ["r1", "r2"]


def test_match_found_payload_returns_opponent_rating_for_each_viewer():
    player1_id = uuid.uuid4()
    player2_id = uuid.uuid4()
    duel_id = uuid.uuid4()
    match = {
        "duel_id": duel_id,
        "player1_id": player1_id,
        "player2_id": player2_id,
        "player1_rating": 1520.0,
        "player2_rating": 1675.0,
        "difficulty": "medium",
    }

    payload1 = _match_found_payload(match, player1_id)
    payload2 = _match_found_payload(match, player2_id)

    assert payload1["duel_id"] == str(duel_id)
    assert payload1["opponent_rating"] == 1675.0
    assert payload2["opponent_rating"] == 1520.0
