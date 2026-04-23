from types import SimpleNamespace

from app.services.crm_followup import (
    infer_followup_outcome,
    should_create_followup,
)
from app.services.session_state import normalize_session_outcome


def _session(*, details=None, timeline=None):
    return SimpleNamespace(
        scoring_details=details,
        emotion_timeline=timeline,
    )


def test_followup_created_for_callback_outcome():
    assert should_create_followup("callback") is True
    assert should_create_followup("continue_next_call") is True
    assert should_create_followup("continue") is True


def test_followup_not_created_for_terminal_negative_outcome():
    assert should_create_followup("hangup") is False
    assert should_create_followup("hostile") is False


def test_normalize_center_outcome_aliases():
    assert normalize_session_outcome("agreed") == "deal_agreed"
    assert normalize_session_outcome("not agreed") == "deal_not_agreed"
    assert normalize_session_outcome("continue_later") == "continue_next_call"


def test_infer_followup_outcome_prefers_scoring_details():
    session = _session(
        details={"call_outcome": "callback"},
        timeline=[{"state": "hangup"}],
    )
    assert infer_followup_outcome(session) == "callback"


def test_infer_followup_outcome_uses_last_emotion_state():
    session = _session(
        details={},
        timeline=[{"state": "guarded"}, {"state": "considering"}],
    )
    assert infer_followup_outcome(session) == "considering"
    assert should_create_followup(infer_followup_outcome(session)) is True
