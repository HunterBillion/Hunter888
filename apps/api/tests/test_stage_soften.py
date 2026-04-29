"""User-first §A: stage tracker prompt softening.

Pins the contract that:
  * with CALL_HUMANIZED_V2 OFF, the prompt keeps the legacy imperative
    ("ПОВЕДЕНИЕ НА ЭТОМ ЭТАПЕ:") — bit-for-bit pre-Sprint-0
  * with the flag ON, the prompt switches to descriptive framing
    ("ЕСТЕСТВЕННОЕ СОСТОЯНИЕ КЛИЕНТА В ЭТОТ МОМЕНТ:") AND adds an
    explicit off-script permission so the AI no longer slaps the manager
    back to the checklist when he asks something unrelated.
"""

from unittest.mock import patch
from app.services.stage_tracker import StageTracker, StageState


def _state(stage: int = 1, name: str = "greeting", completed: list[int] | None = None):
    return StageState(
        current_stage=stage,
        current_stage_name=name,
        stages_completed=completed or [],
        total_stages=7,
        stage_message_counts={},
    )


def test_legacy_prompt_when_flag_off():
    """Bit-for-bit identical to pre-Sprint-0 — no behaviour drift on env miss."""
    tracker = StageTracker("sess1", redis=None)
    with patch("app.config.settings") as s:
        s.call_humanized_v2 = False
        out = tracker.build_stage_prompt(_state())
    assert "ПОВЕДЕНИЕ НА ЭТОМ ЭТАПЕ:" in out
    assert "ЧТО МОЖЕШЬ РАСКРЫТЬ:" in out
    assert "ЕСТЕСТВЕННОЕ СОСТОЯНИЕ" not in out
    assert "не возвращай его" not in out


def test_softened_prompt_when_flag_on():
    """Sprint 0 §A: descriptive frame + off-script permission."""
    tracker = StageTracker("sess1", redis=None)
    with patch("app.config.settings") as s:
        s.call_humanized_v2 = True
        out = tracker.build_stage_prompt(_state())
    assert "ЕСТЕСТВЕННОЕ СОСТОЯНИЕ КЛИЕНТА" in out
    assert "ЧТО УМЕСТНО РАСКРЫТЬ ПО НАСТРОЕНИЮ:" in out
    # Critical: the off-script permission must be present and explicit.
    assert "не возвращай его на этап" in out.lower() or "не возвращай его" in out
    assert "по его вопросу" in out.lower()
    # And the legacy imperative MUST be gone in this mode.
    assert "ПОВЕДЕНИЕ НА ЭТОМ ЭТАПЕ:" not in out


def test_post_completion_prompt_unchanged_in_both_modes():
    """When all stages are done the prompt is the same in both modes —
    no script left to lock onto."""
    tracker = StageTracker("sess1", redis=None)
    done_state = _state(stage=99)  # past total_stages
    with patch("app.config.settings") as s:
        s.call_humanized_v2 = False
        off = tracker.build_stage_prompt(done_state)
    with patch("app.config.settings") as s:
        s.call_humanized_v2 = True
        on = tracker.build_stage_prompt(done_state)
    assert off == on
    assert "Все этапы скрипта пройдены" in off


def test_trap_categories_preserved_in_both_modes():
    """The trap-category line is shared by both modes — scoring relies on
    it. Softening must not drop the trap signal."""
    tracker = StageTracker("sess1", redis=None)
    qual_state = _state(stage=3, name="qualification")  # has emotional+manipulative traps
    with patch("app.config.settings") as s:
        s.call_humanized_v2 = False
        off = tracker.build_stage_prompt(qual_state)
    with patch("app.config.settings") as s:
        s.call_humanized_v2 = True
        on = tracker.build_stage_prompt(qual_state)
    assert "АКТИВНЫЕ КАТЕГОРИИ ЛОВУШЕК:" in off
    assert "АКТИВНЫЕ КАТЕГОРИИ ЛОВУШЕК:" in on


def test_stage_progress_lines_preserved_in_both_modes():
    """The "только начался / начальная / продвинутая" line is identical —
    that's neutral context, not directive, and stays shared."""
    tracker = StageTracker("sess1", redis=None)
    fresh = _state(completed=[])
    with patch("app.config.settings") as s:
        s.call_humanized_v2 = False
        off = tracker.build_stage_prompt(fresh)
    with patch("app.config.settings") as s:
        s.call_humanized_v2 = True
        on = tracker.build_stage_prompt(fresh)
    # Same neutral line in both.
    assert "Разговор только начался." in off
    assert "Разговор только начался." in on
