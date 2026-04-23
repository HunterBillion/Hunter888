from app.services.session_state import (
    is_call_like_mode,
    normalize_session_mode,
    normalize_session_outcome,
    validate_terminal_outcome,
)


def test_session_mode_contract():
    assert normalize_session_mode("chat") == "chat"
    assert normalize_session_mode("call") == "call"
    assert normalize_session_mode("center") == "center"
    assert normalize_session_mode("bad") is None


def test_center_is_call_like_for_prompting():
    assert is_call_like_mode("call") is True
    assert is_call_like_mode("center") is True
    assert is_call_like_mode("chat") is False


def test_center_terminal_outcome_guard():
    assert validate_terminal_outcome(mode="center", outcome="agreed") == (True, "deal_agreed")
    assert validate_terminal_outcome(mode="center", outcome="not_agreed") == (True, "deal_not_agreed")
    assert validate_terminal_outcome(mode="center", outcome="continue") == (True, "continue_next_call")
    assert validate_terminal_outcome(mode="center", outcome=None) == (False, None)


def test_non_center_terminal_outcome_is_not_blocking():
    assert validate_terminal_outcome(mode="call", outcome=None) == (True, None)
    assert normalize_session_outcome("continue later") == "continue_next_call"
