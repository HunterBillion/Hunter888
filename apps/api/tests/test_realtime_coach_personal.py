"""PR-D tests for the personalised weak-area whisper.

Pre-fix the AI coach was generic — every trainee saw the same
«не используй давление» / «задай открытый вопрос» hints regardless of
their past performance. PR-D feeds rag_feedback.get_user_weak_areas
into the whisper engine so a manager whose weakest category is
«qualification» gets a heads-up the moment they enter that stage.
"""
from __future__ import annotations

from app.services.whisper_engine import WhisperEngine


def _make_weak(category: str, error_rate: float, total: int = 12) -> dict:
    return {"category": category, "error_rate": error_rate, "total_answers": total}


def test_personal_whisper_fires_on_matching_stage_within_window():
    """Manager just entered 'qualification' AND has 65% error rate
    in qualification — fire the personal heads-up."""
    eng = WhisperEngine()
    w = eng._check_personal_weakness(
        weak_areas=[_make_weak("qualification", 0.65)],
        current_stage="qualification",
        stage_message_count=1,
    )
    assert w is not None
    assert w.type == "personal"
    assert "слабый этап" in w.message
    assert "qualification" in w.message
    assert "65" in w.message  # rate surfaced as percent


def test_personal_whisper_silent_after_window():
    """Past turn 3 of the stage the heads-up is too late — manager
    is committed to whatever they're doing."""
    eng = WhisperEngine()
    w = eng._check_personal_weakness(
        weak_areas=[_make_weak("qualification", 0.7)],
        current_stage="qualification",
        stage_message_count=5,
    )
    assert w is None


def test_personal_whisper_silent_below_error_rate():
    """40% is the «soft» threshold — anything below isn't a real
    weakness, just normal variance."""
    eng = WhisperEngine()
    w = eng._check_personal_weakness(
        weak_areas=[_make_weak("qualification", 0.3)],
        current_stage="qualification",
        stage_message_count=1,
    )
    assert w is None


def test_personal_whisper_silent_when_stage_doesnt_match():
    """Manager is at greeting but their weak area is closing — no
    fire (different stage = different lesson)."""
    eng = WhisperEngine()
    w = eng._check_personal_weakness(
        weak_areas=[_make_weak("closing", 0.7)],
        current_stage="greeting",
        stage_message_count=1,
    )
    assert w is None


def test_personal_whisper_picks_worst_match():
    """If multiple weak areas map to the same stage, surface the
    worst-performing one — the trainee should see the highest-impact
    issue, not a random one."""
    eng = WhisperEngine()
    w = eng._check_personal_weakness(
        weak_areas=[
            _make_weak("qualification", 0.5),
            _make_weak("discovery", 0.85),  # discovery → qualification stage
        ],
        current_stage="qualification",
        stage_message_count=1,
    )
    assert w is not None
    assert "85" in w.message  # the higher rate wins


def test_personal_whisper_silent_with_empty_areas():
    """Defensive: empty / None list — no fire, no crash."""
    eng = WhisperEngine()
    assert eng._check_personal_weakness([], "qualification", 1) is None


def test_personal_whisper_silent_no_stage_count():
    """Without a stage_message_count we can't distinguish heads-up
    from late-warning — fire defensively (turn 0 is "just entered")."""
    eng = WhisperEngine()
    w = eng._check_personal_weakness(
        weak_areas=[_make_weak("qualification", 0.7)],
        current_stage="qualification",
        stage_message_count=None,
    )
    assert w is not None  # without count = treat as fresh entry
