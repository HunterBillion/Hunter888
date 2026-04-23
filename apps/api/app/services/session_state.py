from __future__ import annotations


SESSION_MODES = {"chat", "call", "center"}
CALL_LIKE_MODES = {"call", "center"}

CENTER_TERMINAL_OUTCOMES = {
    "deal_agreed",
    "deal_not_agreed",
    "continue_next_call",
}

OUTCOME_ALIASES = {
    "agreed": "deal_agreed",
    "contract_agreed": "deal_agreed",
    "contract_signed": "deal_agreed",
    "not_agreed": "deal_not_agreed",
    "contract_not_agreed": "deal_not_agreed",
    "rejected": "deal_not_agreed",
    "continue": "continue_next_call",
    "continue_in_next_call": "continue_next_call",
    "continue_later": "continue_next_call",
    "needs_follow_up": "needs_followup",
}


def normalize_session_mode(mode: object) -> str | None:
    if mode is None:
        return None
    normalized = str(mode).strip().lower().replace(" ", "_")
    return normalized if normalized in SESSION_MODES else None


def is_call_like_mode(mode: object) -> bool:
    return normalize_session_mode(mode) in CALL_LIKE_MODES


def normalize_session_outcome(outcome: object) -> str | None:
    if outcome is None:
        return None
    normalized = str(outcome).strip().lower().replace(" ", "_")
    if not normalized or normalized == "unknown":
        return None
    return OUTCOME_ALIASES.get(normalized, normalized)


def validate_terminal_outcome(*, mode: object, outcome: object) -> tuple[bool, str | None]:
    normalized_mode = normalize_session_mode(mode)
    normalized_outcome = normalize_session_outcome(outcome)
    if normalized_mode != "center":
        return True, normalized_outcome
    return normalized_outcome in CENTER_TERMINAL_OUTCOMES, normalized_outcome
