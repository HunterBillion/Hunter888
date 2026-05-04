"""P4 — judge red_flags / strengths anchored to transcript.

The schema upgrade is **backwards-compatible**: cached old-shape verdicts
(red_flags as ``list[str]``) are normalised on read into the new
anchored shape so the FE doesn't crash when the judge cache TTL spans
the upgrade.
"""
from __future__ import annotations

import json

import pytest


# ── Helper normalisation ────────────────────────────────────────────────────


def test_normalize_legacy_strings() -> None:
    from app.services.scoring_llm_judge import _normalize_judge_dict

    legacy = {
        "verdict": "poor",
        "score_adjust": -3,
        "rationale_ru": "плохо",
        "red_flags": ["оскорбил клиента", "не задал вопросов"],
        "strengths": ["вежливо завершил"],
    }
    out = _normalize_judge_dict(legacy)
    assert out is not None
    assert out["red_flags"] == [
        {"label": "оскорбил клиента", "message_index": -1, "excerpt": "", "fix_example": ""},
        {"label": "не задал вопросов", "message_index": -1, "excerpt": "", "fix_example": ""},
    ]
    assert out["strengths"] == [
        {"label": "вежливо завершил", "message_index": -1, "excerpt": ""},
    ]


def test_normalize_passes_objects_through() -> None:
    from app.services.scoring_llm_judge import _normalize_judge_dict

    new = {
        "red_flags": [{"label": "X", "message_index": 3, "excerpt": "abc", "fix_example": "def"}],
        "strengths": [{"label": "Y", "message_index": 1, "excerpt": "qq"}],
    }
    out = _normalize_judge_dict(new)
    assert out is not None
    assert out["red_flags"][0]["message_index"] == 3
    assert out["strengths"][0]["excerpt"] == "qq"


def test_normalize_handles_mixed() -> None:
    from app.services.scoring_llm_judge import _normalize_judge_dict

    mixed = {"red_flags": ["str-flag", {"label": "obj-flag", "message_index": 2}]}
    out = _normalize_judge_dict(mixed)
    assert out is not None
    assert out["red_flags"][0]["label"] == "str-flag"
    assert out["red_flags"][0]["message_index"] == -1
    assert out["red_flags"][1]["label"] == "obj-flag"
    assert out["red_flags"][1]["message_index"] == 2


# ── Pydantic schema ─────────────────────────────────────────────────────────


def test_judge_verdict_validates_new_shape() -> None:
    from app.services.scoring_llm_judge import JudgeVerdict

    payload = {
        "verdict": "poor",
        "score_adjust": -5,
        "rationale_ru": "грубо",
        "red_flags": [{"label": "грубость", "message_index": 4, "excerpt": "вы что", "fix_example": "Давайте"}],
        "strengths": [],
        "model_used": "claude-haiku",
        "latency_ms": 1500,
    }
    v = JudgeVerdict.model_validate(payload)
    assert v.verdict == "poor"
    assert v.red_flags[0].label == "грубость"
    assert v.red_flags[0].message_index == 4
    assert v.red_flags[0].excerpt == "вы что"
    assert v.red_flags[0].fix_example == "Давайте"


# ── _parse_verdict + index clamping ─────────────────────────────────────────


def test_parse_verdict_legacy_strings_normalised() -> None:
    """Old cached verdicts (list[str]) must parse without crashing."""
    from app.services.scoring_llm_judge import _parse_verdict

    raw = json.dumps({
        "verdict": "good",
        "score_adjust": 2,
        "rationale_ru": "ок",
        "red_flags": ["мелочь"],
        "strengths": ["норм"],
    })
    v = _parse_verdict(raw, model_used="test", latency_ms=10, user_messages_count=5)
    assert v.verdict == "good"
    assert v.red_flags[0].label == "мелочь"
    assert v.red_flags[0].message_index == -1


def test_parse_verdict_clamps_out_of_range_message_index() -> None:
    """LLM hallucinated index 99 with only 5 messages → clamp to -1."""
    from app.services.scoring_llm_judge import _parse_verdict

    raw = json.dumps({
        "verdict": "poor",
        "score_adjust": -3,
        "rationale_ru": "плохо",
        "red_flags": [
            {"label": "X", "message_index": 99, "excerpt": "q", "fix_example": "f"},
            {"label": "Y", "message_index": 2, "excerpt": "z", "fix_example": "g"},
        ],
        "strengths": [],
    })
    v = _parse_verdict(raw, model_used="test", latency_ms=10, user_messages_count=5)
    assert v.red_flags[0].message_index == -1  # clamped
    assert v.red_flags[1].message_index == 2   # in range, kept


def test_parse_verdict_score_adjust_clamped() -> None:
    """LLM returned -50; must clamp to -8 (minimum), still parse."""
    from app.services.scoring_llm_judge import _parse_verdict

    raw = json.dumps({
        "verdict": "red_flag",
        "score_adjust": -50,
        "rationale_ru": "критично",
        "red_flags": [],
        "strengths": [],
    })
    v = _parse_verdict(raw, model_used="test", latency_ms=10, user_messages_count=10)
    assert v.score_adjust == -8


def test_parse_verdict_invalid_json_returns_fallback() -> None:
    """Non-JSON / partial → neutral fallback verdict, not a crash."""
    from app.services.scoring_llm_judge import _parse_verdict, _PARSE_FAIL_RATIONALE

    v = _parse_verdict("not json {{{", model_used="test", latency_ms=10)
    assert v.verdict == "mixed"
    assert v.score_adjust == 0
    assert v.rationale_ru == _PARSE_FAIL_RATIONALE
