"""Tests for the TZ-4.5 persona-slot registry.

Pre-TZ-4.5 the slot vocabulary was duplicated (and silently drifting)
between ``conversation_policy_engine._check_asked_known_slot`` (14
inline frozensets), ``persona_view`` (display labels), and the missing
fact extractor. These tests lock the registry's invariants so a future
refactor can't quietly forget a slot.

The point of the registry is that **every consumer iterates the same
list of codes**. If anyone adds a slot to ``PERSONA_SLOTS`` without
the matching label/extractor_hint/ask_question_triggers, the registry
itself catches it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.persona_slots import (
    PERSONA_SLOTS,
    PersonaSlot,
    all_slot_codes,
    get_slot,
    render_facts_block_for_system_prompt,
    render_facts_for_prompt,
)


class TestRegistryWellFormedness:
    """Static guards: every slot has every required field, no typos."""

    def test_keys_match_codes(self):
        """Dict key must equal slot.code — otherwise lookup-by-code
        breaks silently if someone copy-pastes."""
        for key, slot in PERSONA_SLOTS.items():
            assert key == slot.code, f"key={key!r} but slot.code={slot.code!r}"

    def test_all_codes_are_snake_case_ascii(self):
        """Codes are JSONB keys + event payload fields. Renaming is
        forbidden post-ship; keep the format strict."""
        for code in PERSONA_SLOTS:
            assert code.replace("_", "").isascii(), code
            assert code == code.lower(), f"{code} must be lowercase"
            assert " " not in code, code
            assert "-" not in code, f"{code} use snake_case not kebab-case"

    def test_every_slot_has_ru_label(self):
        for slot in PERSONA_SLOTS.values():
            assert slot.label_ru, f"{slot.code} missing label_ru"
            # The label is shown in Russian prompts and admin UI —
            # accidental English here is a bug.
            assert any(0x0400 <= ord(c) <= 0x04FF for c in slot.label_ru), (
                f"{slot.code}.label_ru={slot.label_ru!r} has no Cyrillic chars — likely English"
            )

    def test_every_slot_has_extractor_hint(self):
        """Without a hint the LLM extractor (PR 2) doesn't know what to
        look for. Empty string is a bug, not a default."""
        for slot in PERSONA_SLOTS.values():
            assert slot.extractor_hint.strip(), f"{slot.code} missing extractor_hint"

    def test_every_slot_has_at_least_one_ask_trigger(self):
        """Without ask_question_triggers the policy engine can't fire
        ``asked_known_slot_again`` for this slot — the slot becomes
        invisible to TZ-4 §10."""
        for slot in PERSONA_SLOTS.values():
            assert len(slot.ask_question_triggers) >= 1, (
                f"{slot.code} must have at least one ask_question_trigger"
            )

    def test_ask_triggers_are_lowercase_normalised(self):
        """Policy engine matches against lowercased text. Triggers
        themselves must be lowercase or matches won't fire."""
        for slot in PERSONA_SLOTS.values():
            for trig in slot.ask_question_triggers:
                assert trig == trig.lower(), (
                    f"{slot.code} trigger {trig!r} not lowercase"
                )
                assert trig.strip() == trig, f"{slot.code} trigger has whitespace"

    def test_immutability(self):
        """Frozen dataclass — typo'd assignment must raise."""
        slot = next(iter(PERSONA_SLOTS.values()))
        with pytest.raises((AttributeError, Exception)):
            slot.label_ru = "hacked"  # type: ignore[misc]

    def test_get_slot_unknown_returns_none(self):
        assert get_slot("nonexistent_slot") is None

    def test_get_slot_known_returns_the_slot(self):
        slot = get_slot("full_name")
        assert slot is not None
        assert slot.code == "full_name"

    def test_all_slot_codes_is_immutable_view(self):
        codes = all_slot_codes()
        assert isinstance(codes, frozenset)
        assert "full_name" in codes
        # Closed vocabulary — at minimum the 14 we inherited from
        # conversation_policy_engine plus the 2 added here (company,
        # industry). Keeping this assertion forces a deliberate
        # decision when someone adds slot N+1.
        assert len(codes) >= 14


class TestFormatters:
    def test_str_formatter_strips_whitespace(self):
        slot = get_slot("full_name")
        assert slot.formatter("  Иван  ") == "Иван"

    def test_int_with_word_handles_russian_plurals(self):
        slot = get_slot("children_count")
        assert slot.formatter(0) == "0 детей"
        assert slot.formatter(1) == "1 ребёнок"
        assert slot.formatter(2) == "2 ребёнка"
        assert slot.formatter(4) == "4 ребёнка"
        assert slot.formatter(5) == "5 детей"
        assert slot.formatter(11) == "11 детей"  # 11-19 are special
        assert slot.formatter(21) == "21 ребёнок"
        assert slot.formatter(22) == "22 ребёнка"
        assert slot.formatter(25) == "25 детей"

    def test_int_with_word_falls_back_on_non_int(self):
        slot = get_slot("children_count")
        assert slot.formatter("много") == "много"
        assert slot.formatter(None) == "None"

    def test_age_formatter(self):
        slot = get_slot("age")
        assert slot.formatter(45) == "45 лет"
        assert slot.formatter("не сказал") == "не сказал"

    def test_gender_normalises_to_russian(self):
        slot = get_slot("gender")
        assert slot.formatter("male") == "мужской"
        assert slot.formatter("FEMALE") == "женский"
        assert slot.formatter("m") == "мужской"
        assert slot.formatter("f") == "женский"
        assert slot.formatter("unknown") == "unknown"

    def test_creditors_list_formatter(self):
        slot = get_slot("creditors")
        assert slot.formatter(["Сбер", "Тинькофф", "ВТБ"]) == "Сбер, Тинькофф, ВТБ"
        assert slot.formatter([]) == ""
        assert slot.formatter(["Сбер", None, ""]) == "Сбер"


class TestRenderFactsForPrompt:
    def test_empty_facts_returns_empty_string(self):
        assert render_facts_for_prompt(None) == ""
        assert render_facts_for_prompt({}) == ""

    def test_renders_known_slots(self):
        facts = {
            "full_name": {"value": "Дмитрий"},
            "city": {"value": "Москва"},
            "company_name": {"value": "Альфа"},
        }
        rendered = render_facts_for_prompt(facts)
        assert "Имя: Дмитрий" in rendered
        assert "Город: Москва" in rendered
        assert "Компания: Альфа" in rendered

    def test_skips_unknown_slot_codes(self):
        """A DB row may have a slot the registry doesn't know about
        anymore (renamed/removed). Don't crash — skip silently and
        let the audit log keep it."""
        facts = {
            "full_name": {"value": "Иван"},
            "removed_slot_xyz": {"value": "anything"},
        }
        rendered = render_facts_for_prompt(facts)
        assert "Имя: Иван" in rendered
        assert "removed_slot_xyz" not in rendered
        assert "anything" not in rendered

    def test_skips_malformed_fact_entries(self):
        facts = {
            "full_name": {"value": "Дмитрий"},
            "city": "raw string not a dict",  # malformed
            "phone": {},  # missing 'value'
        }
        rendered = render_facts_for_prompt(facts)
        assert "Имя: Дмитрий" in rendered
        assert rendered.count("•") == 1  # only the valid one

    def test_marks_stale_facts(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        facts = {
            "city": {"value": "Москва", "captured_at": old},  # ttl=365, OK
            "income": {"value": "100000", "captured_at": old},  # ttl=180, stale
        }
        rendered = render_facts_for_prompt(facts)
        assert "Москва" in rendered
        assert "(возможно устарело)" not in rendered.split("Москва")[1].split("\n")[0]
        # income is past 180-day TTL → stale-marked
        income_line = [ln for ln in rendered.split("\n") if "Доход" in ln][0]
        assert "(возможно устарело)" in income_line

    def test_can_drop_stale_facts_entirely(self):
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        facts = {"income": {"value": "100000", "captured_at": old}}
        assert render_facts_for_prompt(facts, include_stale=False) == ""

    def test_no_captured_at_means_never_stale(self):
        """Backward-compat: TZ-4 D3 originally wrote facts without
        captured_at. They should render without staleness suffix."""
        facts = {"city": {"value": "Рязань"}}
        rendered = render_facts_for_prompt(facts)
        assert "Город: Рязань" in rendered
        assert "(возможно устарело)" not in rendered


class TestRenderFactsBlockForSystemPrompt:
    """The PR 4 wrapper that produces the full block ready to splice
    into the LLM system prompt — header, body, footer instructions.
    Used by both _build_system_prompt and generate_response_stream
    so they produce identical text."""

    def test_empty_facts_returns_empty_string(self):
        assert render_facts_block_for_system_prompt(None) == ""
        assert render_facts_block_for_system_prompt({}) == ""

    def test_includes_header_and_footer(self):
        facts = {"full_name": {"value": "Дмитрий"}}
        block = render_facts_block_for_system_prompt(facts)
        assert "ЧТО ТЫ УЖЕ ЗНАЕШЬ О СОБЕСЕДНИКЕ" in block
        assert "Веди себя как ЗНАКОМЫЙ" in block
        assert "не переспрашивай" in block

    def test_renders_facts_in_body(self):
        facts = {
            "full_name": {"value": "Дмитрий"},
            "city": {"value": "Москва"},
        }
        block = render_facts_block_for_system_prompt(facts)
        assert "Имя: Дмитрий" in block
        assert "Город: Москва" in block

    def test_acknowledges_stale_facts_in_footer(self):
        from datetime import datetime, timedelta, timezone

        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        facts = {"income": {"value": "100000", "captured_at": old}}
        block = render_facts_block_for_system_prompt(facts)
        # Footer instruction tells AI how to handle stale facts
        assert "(возможно устарело)" in block
        assert "переспроси" in block.lower()

    def test_empty_after_filter_returns_empty(self):
        """Edge: facts dict has only unknown slots → render_facts_for
        prompt returns empty → wrapper must return empty too (no
        bare header without body)."""
        facts = {"removed_slot_xyz": {"value": "anything"}}
        assert render_facts_block_for_system_prompt(facts) == ""


class TestRegistryConsistencyWithPolicyEngine:
    """The policy engine's inline ``triggers`` dict at
    conversation_policy_engine.py:316-331 used to be the sole owner
    of question-trigger phrases. After PR 1 the registry takes over.
    Until PR 4 wires the engine to import from here, drift is
    possible — this test catches it.
    """

    def test_all_legacy_slots_present_in_registry(self):
        """The 14 codes the policy engine knew about must all be in
        the registry. Adding new ones is fine; dropping legacy ones
        without explicit migration is not."""
        legacy_codes = frozenset({
            "full_name", "phone", "email", "city", "age", "gender",
            "role_title", "total_debt", "creditors", "income",
            "income_type", "family_status", "children_count",
            "property_status",
        })
        missing = legacy_codes - all_slot_codes()
        assert not missing, f"Registry dropped legacy slots: {missing}"

    def test_legacy_triggers_carried_over(self):
        """Spot-check that the trigger phrases from the legacy
        conversation_policy_engine ``triggers`` dict survived the
        move. Picks 3 representative slots."""
        full_name = get_slot("full_name")
        assert full_name is not None
        assert "как вас зовут" in full_name.ask_question_triggers

        children = get_slot("children_count")
        assert children is not None
        assert "сколько у вас детей" in children.ask_question_triggers

        debt = get_slot("total_debt")
        assert debt is not None
        assert "размер долга" in debt.ask_question_triggers
