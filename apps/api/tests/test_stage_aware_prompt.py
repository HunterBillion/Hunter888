"""PR-B (Stage-aware AI) — render tests.

Pre-fix the AI client had no idea which sales-funnel stage the
manager was on. Personas dumped objections during greeting and recapped
their company during close. These tests fail on pre-fix code (no
``current_stage_info`` parameter / no rendered block) and pass after
PR-B.
"""
from __future__ import annotations

from app.services.llm import _build_system_prompt, _render_stage_awareness_block


def test_stage_block_minimal_renders_label_and_index():
    """The most basic case: just stage_name + label + index. The block
    must say where the manager is on the funnel so the AI doesn't try
    to recap company info during the close, etc."""
    out = _render_stage_awareness_block({
        "stage_name": "presentation",
        "stage_label": "Презентация",
        "stage_index": 4,
        "total_stages": 7,
    })
    assert "## Структура разговора" in out
    assert "Презентация" in out
    assert "4 из 7" in out


def test_stage_block_lists_completed_stages_with_labels():
    """Completed stages must be human-readable Russian labels, not
    raw STAGE_ORDER keys — the LLM produces better Russian when it
    sees Russian context."""
    out = _render_stage_awareness_block({
        "stage_name": "objections",
        "stage_label": "Возражения",
        "stage_index": 5,
        "total_stages": 7,
        "stages_completed": ["greeting", "contact", "qualification", "presentation"],
    })
    assert "Уже пройдено:" in out
    assert "Приветствие" in out
    assert "Контакт" in out
    # Raw key shouldn't leak — these must be translated.
    assert "greeting" not in out
    assert "qualification" not in out


def test_stage_block_emits_skip_warning_with_skipped_stages():
    """Stage-skip detection. Manager jumped from greeting straight to
    closing → AI should be primed to push back («подождите, я даже не
    понял что вы предлагаете»)."""
    out = _render_stage_awareness_block({
        "stage_name": "closing",
        "stage_label": "Закрытие",
        "stage_index": 7,
        "total_stages": 7,
        "skipped_stages": ["qualification", "presentation"],
    })
    assert "пропустил" in out
    assert "Квалификация" in out
    assert "Презентация" in out
    # The block must guide the AI to react — not just inform it.
    assert "подождите" in out.lower() or "не понял" in out.lower()


def test_stage_block_emits_stall_warning_after_5_messages():
    """If manager spins on the same stage for 5+ turns the AI should
    start losing patience («давайте к делу»)."""
    out = _render_stage_awareness_block({
        "stage_name": "greeting",
        "stage_label": "Приветствие",
        "stage_index": 1,
        "total_stages": 7,
        "messages_on_stage": 6,
    })
    assert "задержался" in out
    assert "6+" in out
    assert "терять терпение" in out


def test_stage_block_no_stall_warning_below_threshold():
    """Defensive: 1-4 messages on stage is normal, no patience signal."""
    out = _render_stage_awareness_block({
        "stage_name": "qualification",
        "stage_label": "Квалификация",
        "stage_index": 3,
        "total_stages": 7,
        "messages_on_stage": 3,
    })
    assert "задержался" not in out
    assert "терпение" not in out


def test_stage_block_empty_when_no_stage():
    """Pre-stage-detection (very first user message) — return empty
    so we don't pollute the system prompt with a stage header that
    has no body."""
    out = _render_stage_awareness_block({})
    assert out == ""


def test_build_system_prompt_threads_stage_info():
    """The block must actually appear in the assembled system prompt
    when ``current_stage_info`` is supplied."""
    out = _build_system_prompt(
        character_prompt="Ты Сергей, директор.",
        guardrails="",
        emotion_state="cold",
        current_stage_info={
            "stage_name": "presentation",
            "stage_label": "Презентация",
            "stage_index": 4,
            "total_stages": 7,
            "stages_completed": ["greeting", "contact"],
        },
    )
    assert "Структура разговора" in out
    assert "Презентация" in out
    assert "Приветствие" in out


def test_build_system_prompt_no_stage_block_without_info():
    """Backward compat: caller can omit current_stage_info and the
    output stays clean (no stray stage section)."""
    out = _build_system_prompt(
        character_prompt="x",
        guardrails="",
        emotion_state="cold",
    )
    assert "Структура разговора" not in out
