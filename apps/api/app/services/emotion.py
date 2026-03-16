"""Character emotion engine (3 states for MVP-0).

States: cold → warming → open
Transitions depend on manager's communication quality.

Will be fully implemented in Phase 2.
"""

from app.models.character import EmotionState

TRANSITIONS = {
    EmotionState.cold: {
        "good_response": EmotionState.warming,
        "bad_response": EmotionState.cold,
    },
    EmotionState.warming: {
        "good_response": EmotionState.open,
        "bad_response": EmotionState.cold,
    },
    EmotionState.open: {
        "good_response": EmotionState.open,
        "bad_response": EmotionState.warming,
    },
}


def get_next_emotion(current: EmotionState, response_quality: str) -> EmotionState:
    return TRANSITIONS.get(current, {}).get(response_quality, current)
