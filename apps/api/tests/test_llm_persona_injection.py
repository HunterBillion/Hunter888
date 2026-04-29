"""TZ-4.5 PR 4 — verify _build_system_prompt injects persona facts.

The point of this PR: when the AI client's system prompt is built,
the facts the extractor wrote in PR 3 must end up inside the prompt
text. This test pins the contract — break it and the AI silently
goes back to cold-start mode for every call.

We test the lower-level _build_system_prompt directly (not
generate_response) because:
  * generate_response has 60+ lines of provider-routing/lorebook/
    A-B-test logic before it touches the system prompt — too much
    surface to mock for a one-line behavioural assertion
  * _build_system_prompt is pure (no IO, no SDK) — fast unit test
"""

from __future__ import annotations

from app.services.llm import _build_system_prompt


class TestBuildSystemPromptPersonaFacts:
    def test_no_facts_no_block(self):
        """Backward-compat: callers that don't pass persona_facts
        (cold start, anti_cheat coach, etc.) must see no facts block."""
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
        )
        assert "ЧТО ТЫ УЖЕ ЗНАЕШЬ" not in out

    def test_empty_facts_dict_no_block(self):
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
            persona_facts={},
        )
        assert "ЧТО ТЫ УЖЕ ЗНАЕШЬ" not in out

    def test_facts_appear_in_prompt(self):
        """Sanity: facts dict → AI sees them in system prompt."""
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="curious",
            persona_facts={
                "full_name": {"value": "Дмитрий"},
                "city": {"value": "Москва"},
                "company_name": {"value": "Альфа"},
            },
        )
        assert "ЧТО ТЫ УЖЕ ЗНАЕШЬ О СОБЕСЕДНИКЕ" in out
        assert "Имя: Дмитрий" in out
        assert "Город: Москва" in out
        assert "Компания: Альфа" in out
        # And the behavioural footer telling the AI how to use them
        assert "Веди себя как ЗНАКОМЫЙ" in out

    def test_facts_block_after_emotion_block(self):
        """Order matters: facts come AFTER emotion behaviour so the
        AI's most recent context is "this person told me X". Putting
        facts before emotion would let an old fact swamp the current
        emotional state."""
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
            persona_facts={"full_name": {"value": "Дмитрий"}},
        )
        emotion_idx = out.find("Текущее эмоциональное состояние")
        facts_idx = out.find("ЧТО ТЫ УЖЕ ЗНАЕШЬ")
        assert emotion_idx >= 0
        assert facts_idx >= 0
        assert facts_idx > emotion_idx, (
            "persona facts block must come AFTER emotion block — "
            "otherwise old facts override fresh emotional context"
        )

    def test_unknown_slot_silently_dropped(self):
        """A DB row may have a slot the registry doesn't know about
        anymore (renamed/removed). Don't crash — skip silently. Other
        valid facts should still render."""
        out = _build_system_prompt(
            character_prompt="character",
            guardrails="guardrails",
            emotion_state="cold",
            persona_facts={
                "full_name": {"value": "Иван"},
                "removed_slot_xyz": {"value": "anything"},
            },
        )
        assert "Имя: Иван" in out
        assert "removed_slot_xyz" not in out
        assert "anything" not in out
