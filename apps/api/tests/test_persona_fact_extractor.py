"""Tests for the TZ-4.5 fact extractor.

Two layers:

1. **Golden parser tests** — feed pre-canned LLM responses through
   ``_parse_response`` and assert the validation gate accepts /
   rejects correctly. Doesn't need the network / Anthropic SDK / a
   real key. These cover ~90% of the extractor's logic surface.

2. **End-to-end mock tests** — patch the Claude client to return
   canned responses and assert the public ``extract_facts_from_turn``
   returns the right ExtractedFact list. Verifies the wiring (system
   prompt build, response unpacking, timeout handling).

We intentionally do NOT test against the live LLM here — that's flaky
and slow. The "does the LLM extract X correctly" loop belongs in the
golden_smoke harness once PR 3 wires the extractor in.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.persona_fact_extractor import (
    ExtractedFact,
    _format_known_facts,
    _parse_response,
    _render_system_prompt,
    _validate_one,
    extract_facts_from_turn,
)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _mock_claude_response(text: str) -> MagicMock:
    """Mimic the shape of an anthropic.types.Message response."""
    block = MagicMock()
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


# ─── _validate_one — strict gate ────────────────────────────────────────────


class TestValidateOne:
    def test_accepts_well_formed_fact(self):
        item = {
            "slot_code": "full_name",
            "value": "Дмитрий",
            "confidence": 0.95,
            "quote": "меня зовут Дмитрий",
        }
        result = _validate_one(item, manager_message="Здравствуйте, меня зовут Дмитрий")
        assert result is not None
        assert result.slot_code == "full_name"
        assert result.value == "Дмитрий"
        assert result.confidence == 0.95
        assert result.quote == "меня зовут Дмитрий"

    def test_rejects_unknown_slot(self):
        item = {
            "slot_code": "favourite_pizza",  # not in registry
            "value": "пепперони",
            "confidence": 0.99,
            "quote": "люблю пепперони",
        }
        assert _validate_one(item, "люблю пепперони") is None

    def test_rejects_missing_required_keys(self):
        item = {"slot_code": "full_name", "value": "Иван"}  # no confidence/quote
        assert _validate_one(item, "меня зовут Иван") is None

    def test_rejects_quote_not_in_message(self):
        """The LLM must not fabricate quotes. If quote isn't a literal
        substring, drop the fact even if it 'sounds right'."""
        item = {
            "slot_code": "city",
            "value": "Москва",
            "confidence": 0.9,
            "quote": "я живу в Москве",  # the actual message says nothing about Moscow
        }
        assert _validate_one(item, "я давно искал такую услугу") is None

    def test_quote_substring_matching_is_case_insensitive(self):
        item = {
            "slot_code": "full_name",
            "value": "Иван",
            "confidence": 0.9,
            "quote": "Меня Зовут Иван",  # mixed case
        }
        # Manager message in lowercase
        assert _validate_one(item, "здравствуйте, меня зовут иван") is not None

    def test_quote_substring_normalises_whitespace(self):
        """Quote with collapsed whitespace should match a message
        with the same words separated by tabs/newlines."""
        item = {
            "slot_code": "full_name",
            "value": "Алексей",
            "confidence": 0.85,
            "quote": "меня зовут Алексей",
        }
        # Message with extra whitespace
        assert _validate_one(item, "меня  зовут\tАлексей,\nприятно познакомиться") is not None

    def test_rejects_out_of_range_confidence(self):
        item = {
            "slot_code": "full_name",
            "value": "Иван",
            "confidence": 1.5,  # > 1.0
            "quote": "меня зовут Иван",
        }
        assert _validate_one(item, "меня зовут Иван") is None

    def test_rejects_negative_confidence(self):
        item = {
            "slot_code": "full_name",
            "value": "Иван",
            "confidence": -0.1,
            "quote": "меня зовут Иван",
        }
        assert _validate_one(item, "меня зовут Иван") is None

    def test_int_slot_coerces_string_value(self):
        """LLM sometimes wraps numbers in strings — coerce when slot
        type is int. children_count is the canonical example."""
        item = {
            "slot_code": "children_count",
            "value": "2",
            "confidence": 0.9,
            "quote": "у меня двое детей",
        }
        result = _validate_one(item, "у меня двое детей")
        assert result is not None
        assert result.value == 2

    def test_int_slot_rejects_non_numeric(self):
        item = {
            "slot_code": "children_count",
            "value": "много",
            "confidence": 0.9,
            "quote": "много детей",
        }
        assert _validate_one(item, "у меня много детей") is None

    def test_list_slot_strips_empty_entries(self):
        item = {
            "slot_code": "creditors",
            "value": ["Сбер", "", None, "Тинькофф"],
            "confidence": 0.85,
            "quote": "должен Сберу и Тинькофф",
        }
        result = _validate_one(item, "должен сберу и тинькофф")
        assert result is not None
        assert result.value == ["Сбер", "Тинькофф"]

    def test_list_slot_rejects_all_empty(self):
        item = {
            "slot_code": "creditors",
            "value": [],
            "confidence": 0.85,
            "quote": "ничего",
        }
        assert _validate_one(item, "ничего") is None

    def test_str_slot_strips_whitespace(self):
        item = {
            "slot_code": "city",
            "value": "  Москва  ",
            "confidence": 0.95,
            "quote": "я из Москвы",
        }
        result = _validate_one(item, "я из Москвы")
        assert result is not None
        assert result.value == "Москва"

    def test_tolerates_extra_keys_from_chatty_llm(self):
        """Some LLMs add an 'explanation' or 'reason' field. Accept
        as long as the four required keys are present."""
        item = {
            "slot_code": "full_name",
            "value": "Иван",
            "confidence": 0.9,
            "quote": "меня зовут Иван",
            "explanation": "manager introduced themselves directly",  # extra
        }
        assert _validate_one(item, "меня зовут Иван") is not None


# ─── _parse_response — JSON tolerance ───────────────────────────────────────


class TestParseResponse:
    def test_clean_json_array(self):
        raw = '[{"slot_code":"full_name","value":"Иван","confidence":0.95,"quote":"меня зовут Иван"}]'
        facts = _parse_response(raw, manager_message="меня зовут Иван")
        assert len(facts) == 1
        assert facts[0].slot_code == "full_name"

    def test_handles_markdown_fence(self):
        raw = '```json\n[{"slot_code":"full_name","value":"Иван","confidence":0.9,"quote":"меня зовут Иван"}]\n```'
        facts = _parse_response(raw, manager_message="меня зовут Иван")
        assert len(facts) == 1

    def test_handles_trailing_text(self):
        """Some LLMs add an explanation after the JSON despite being
        told not to. Find the array and ignore the rest."""
        raw = '[{"slot_code":"city","value":"Рязань","confidence":0.85,"quote":"из Рязани"}]\n\nReason: clear mention.'
        facts = _parse_response(raw, manager_message="я из Рязани, занимаюсь стройкой")
        assert len(facts) == 1
        assert facts[0].slot_code == "city"

    def test_empty_array(self):
        assert _parse_response("[]", manager_message="привет") == []

    def test_empty_string(self):
        assert _parse_response("", manager_message="привет") == []

    def test_no_array_in_response(self):
        """Some LLMs write prose. We drop everything."""
        assert _parse_response("Не нашёл фактов.", manager_message="привет") == []

    def test_malformed_json_drops_everything(self):
        raw = '[{"slot_code":"full_name","value":"Иван",}]'  # trailing comma
        assert _parse_response(raw, "меня зовут Иван") == []

    def test_dedupes_same_slot(self):
        """LLM occasionally double-emits same slot. Keep first."""
        raw = (
            '[{"slot_code":"full_name","value":"Иван","confidence":0.9,"quote":"меня зовут Иван"},'
            '{"slot_code":"full_name","value":"Иван-Петрович","confidence":0.85,"quote":"меня зовут Иван"}]'
        )
        facts = _parse_response(raw, "меня зовут Иван")
        assert len(facts) == 1
        assert facts[0].value == "Иван"

    def test_drops_invalid_keeps_valid(self):
        """Mixed batch: keep good ones, drop bad ones."""
        raw = (
            '[{"slot_code":"full_name","value":"Иван","confidence":0.9,"quote":"меня зовут Иван"},'
            '{"slot_code":"madeup_slot","value":"X","confidence":0.9,"quote":"X"},'
            '{"slot_code":"city","value":"Москва","confidence":0.95,"quote":"из Москвы"}]'
        )
        facts = _parse_response(raw, "меня зовут Иван, я из Москвы")
        assert len(facts) == 2
        assert {f.slot_code for f in facts} == {"full_name", "city"}


# ─── _format_known_facts — context for prompt ───────────────────────────────


class TestFormatKnownFacts:
    def test_empty_returns_placeholder(self):
        assert "пока ничего не известно" in _format_known_facts(None)
        assert "пока ничего не известно" in _format_known_facts({})

    def test_renders_existing_facts(self):
        facts = {
            "full_name": {"value": "Дмитрий"},
            "city": {"value": "Москва"},
        }
        rendered = _format_known_facts(facts)
        assert "Имя: Дмитрий" in rendered
        assert "Город: Москва" in rendered

    def test_skips_unknown_slot_codes(self):
        facts = {
            "full_name": {"value": "Иван"},
            "removed_slot_xyz": {"value": "anything"},
        }
        rendered = _format_known_facts(facts)
        assert "Имя: Иван" in rendered
        assert "removed_slot_xyz" not in rendered


# ─── _render_system_prompt — quick sanity ───────────────────────────────────


class TestRenderSystemPrompt:
    def test_contains_all_slot_codes(self):
        prompt = _render_system_prompt()
        for code in ("full_name", "city", "company_name", "children_count"):
            assert code in prompt, f"slot {code} missing from system prompt"

    def test_mentions_quote_substring_rule(self):
        prompt = _render_system_prompt()
        assert "точная подстрока" in prompt or "точную подстроку" in prompt or "точной подстрокой" in prompt


# ─── extract_facts_from_turn — public API with mocked client ────────────────


class TestExtractFactsFromTurn:
    @pytest.mark.asyncio
    async def test_short_message_skipped_without_calling_llm(self):
        """Vacuous turns ("ага", "да") shouldn't burn an LLM call."""
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock()
        with patch("app.services.llm._get_claude_client", return_value=mock_client):
            result = await extract_facts_from_turn(manager_message="да")
        assert result == []
        mock_client.messages.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_client_returns_empty(self):
        """When Claude API isn't configured, extractor must no-op
        instead of raising. Caller (PR 3) treats empty as 'no new
        facts' and moves on."""
        with patch("app.services.llm._get_claude_client", return_value=None):
            result = await extract_facts_from_turn(
                manager_message="меня зовут Дмитрий, я из Москвы",
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_happy_path_returns_facts(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(
            return_value=_mock_claude_response(
                '[{"slot_code":"full_name","value":"Дмитрий","confidence":0.95,"quote":"меня зовут Дмитрий"},'
                '{"slot_code":"city","value":"Москва","confidence":0.9,"quote":"я из Москвы"}]'
            )
        )
        with patch("app.services.llm._get_claude_client", return_value=mock_client):
            result = await extract_facts_from_turn(
                manager_message="Здравствуйте, меня зовут Дмитрий, я из Москвы, занимаюсь стройкой",
            )
        assert len(result) == 2
        codes = {f.slot_code for f in result}
        assert codes == {"full_name", "city"}

    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self):
        import asyncio as _asyncio

        async def _slow_call(*_args, **_kwargs):
            await _asyncio.sleep(10)
            return _mock_claude_response("[]")

        mock_client = MagicMock()
        mock_client.messages.create = _slow_call
        with patch("app.services.llm._get_claude_client", return_value=mock_client):
            result = await extract_facts_from_turn(
                manager_message="Длинная реплика менеджера про что-то",
                timeout_s=0.1,
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_exception_returns_empty(self):
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("rate limit"))
        with patch("app.services.llm._get_claude_client", return_value=mock_client):
            result = await extract_facts_from_turn(
                manager_message="Длинная реплика менеджера про что-то",
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_passes_known_facts_in_user_prompt(self):
        """Smoke check that confirmed_facts is rendered into the user
        message. We don't pin exact format — just that the value
        appears somewhere."""
        captured_messages = []

        async def _capture(**kwargs):
            captured_messages.append(kwargs.get("messages", []))
            return _mock_claude_response("[]")

        mock_client = MagicMock()
        mock_client.messages.create = _capture
        with patch("app.services.llm._get_claude_client", return_value=mock_client):
            await extract_facts_from_turn(
                manager_message="Длинная реплика менеджера про работу",
                confirmed_facts={"full_name": {"value": "Дмитрий"}},
            )
        assert captured_messages
        user_text = captured_messages[0][0]["content"]
        assert "Дмитрий" in user_text


# ─── ExtractedFact dataclass guards ─────────────────────────────────────────


class TestExtractedFact:
    def test_rejects_out_of_range_confidence(self):
        with pytest.raises(ValueError):
            ExtractedFact(slot_code="full_name", value="X", confidence=1.5, quote="X")
        with pytest.raises(ValueError):
            ExtractedFact(slot_code="full_name", value="X", confidence=-0.1, quote="X")

    def test_frozen(self):
        f = ExtractedFact(slot_code="full_name", value="X", confidence=0.9, quote="X")
        with pytest.raises(Exception):
            f.value = "hacked"  # type: ignore[misc]


# ─── _should_commit — confidence-based commit decision ──────────────────────


class TestShouldCommit:
    """The gate between extracted-fact and lock_slot. Three tiers:
    new/stable-overwrite/volatile-overwrite — verifying each."""

    def test_new_fact_at_floor(self):
        from app.services.persona_fact_extractor import _should_commit

        fact = ExtractedFact(slot_code="full_name", value="Иван", confidence=0.7, quote="меня зовут Иван")
        assert _should_commit(fact, persona_facts={}) is True

    def test_new_fact_below_floor(self):
        from app.services.persona_fact_extractor import _should_commit

        fact = ExtractedFact(slot_code="full_name", value="Иван", confidence=0.69, quote="x")
        # validation gate already enforces ≥ 0.7 in production; this
        # tests the defence-in-depth at the commit layer.
        assert _should_commit(fact, persona_facts={}) is False

    def test_overwrite_stable_below_strict_floor(self):
        """full_name is stable=True; overwrite needs ≥ 0.9."""
        from app.services.persona_fact_extractor import _should_commit

        fact = ExtractedFact(
            slot_code="full_name", value="Алексей", confidence=0.85, quote="зовут Алексей",
        )
        existing = {"full_name": {"value": "Иван"}}
        assert _should_commit(fact, persona_facts=existing) is False

    def test_overwrite_stable_at_strict_floor(self):
        from app.services.persona_fact_extractor import _should_commit

        fact = ExtractedFact(
            slot_code="full_name", value="Алексей", confidence=0.92, quote="зовут Алексей",
        )
        existing = {"full_name": {"value": "Иван"}}
        assert _should_commit(fact, persona_facts=existing) is True

    def test_overwrite_volatile_at_relaxed_floor(self):
        """income is stable=False; overwrite at 0.7 is OK."""
        from app.services.persona_fact_extractor import _should_commit

        fact = ExtractedFact(
            slot_code="income", value="120000", confidence=0.75, quote="зарабатываю 120к",
        )
        existing = {"income": {"value": "100000"}}
        assert _should_commit(fact, persona_facts=existing) is True

    def test_unknown_slot_never_commits(self):
        from app.services.persona_fact_extractor import _should_commit

        fact = ExtractedFact(
            slot_code="favourite_pizza", value="пепперони", confidence=0.99, quote="люблю пепперони",
        )
        assert _should_commit(fact, persona_facts={}) is False

    def test_existing_fact_with_null_value_treated_as_empty(self):
        """Defensive: malformed DB row {"value": None} should be
        treated as 'no existing value' so a new fact can write."""
        from app.services.persona_fact_extractor import _should_commit

        fact = ExtractedFact(
            slot_code="full_name", value="Иван", confidence=0.75, quote="зовут Иван",
        )
        existing = {"full_name": {"value": None}}
        assert _should_commit(fact, persona_facts=existing) is True


# ─── extract_and_commit_facts_for_turn — the public PR 3 wiring ─────────────


class TestExtractAndCommit:
    @pytest.mark.asyncio
    async def test_no_persona_returns_zero(self):
        from app.services.persona_fact_extractor import (
            extract_and_commit_facts_for_turn,
        )

        n = await extract_and_commit_facts_for_turn(
            db=MagicMock(),
            session_id="sid",
            user_id="uid",
            manager_message="меня зовут Иван",
            persona=None,
        )
        assert n == 0

    @pytest.mark.asyncio
    async def test_no_facts_returns_zero(self):
        """Extractor returns []. Wrapper does nothing, no lock_slot call."""
        from app.services.persona_fact_extractor import (
            extract_and_commit_facts_for_turn,
        )

        persona = MagicMock()
        persona.confirmed_facts = {}
        persona.version = 1

        with patch(
            "app.services.persona_fact_extractor.extract_facts_from_turn",
            AsyncMock(return_value=[]),
        ):
            n = await extract_and_commit_facts_for_turn(
                db=MagicMock(),
                session_id="sid",
                user_id="uid",
                manager_message="привет",
                persona=persona,
            )
        assert n == 0

    @pytest.mark.asyncio
    async def test_commits_high_confidence_new_facts(self):
        from app.services.persona_fact_extractor import (
            extract_and_commit_facts_for_turn,
        )

        persona = MagicMock()
        persona.confirmed_facts = {}
        persona.version = 1
        persona.lead_client_id = "lc-1"

        candidates = [
            ExtractedFact("full_name", "Дмитрий", 0.95, "меня зовут Дмитрий"),
            ExtractedFact("city", "Москва", 0.90, "из Москвы"),
        ]

        lock_slot_mock = AsyncMock(return_value=(persona, MagicMock()))
        with patch(
            "app.services.persona_fact_extractor.extract_facts_from_turn",
            AsyncMock(return_value=candidates),
        ), patch(
            "app.services.persona_memory.lock_slot", lock_slot_mock,
        ):
            n = await extract_and_commit_facts_for_turn(
                db=MagicMock(),
                session_id="sid",
                user_id="uid",
                manager_message="меня зовут Дмитрий, я из Москвы",
                persona=persona,
            )
        assert n == 2
        assert lock_slot_mock.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_low_confidence_overwrite_of_stable_slot(self):
        from app.services.persona_fact_extractor import (
            extract_and_commit_facts_for_turn,
        )

        persona = MagicMock()
        persona.confirmed_facts = {"full_name": {"value": "Иван"}}
        persona.version = 1
        persona.lead_client_id = "lc-1"

        # Confidence 0.85 — below stable=True floor of 0.9
        candidates = [ExtractedFact("full_name", "Алексей", 0.85, "зовут Алексей")]

        lock_slot_mock = AsyncMock()
        with patch(
            "app.services.persona_fact_extractor.extract_facts_from_turn",
            AsyncMock(return_value=candidates),
        ), patch(
            "app.services.persona_memory.lock_slot", lock_slot_mock,
        ):
            n = await extract_and_commit_facts_for_turn(
                db=MagicMock(),
                session_id="sid",
                user_id="uid",
                manager_message="зовут Алексей",
                persona=persona,
            )
        assert n == 0
        lock_slot_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_persona_conflict_continues_batch(self):
        from app.services import persona_memory
        from app.services.persona_fact_extractor import (
            extract_and_commit_facts_for_turn,
        )

        persona = MagicMock()
        persona.confirmed_facts = {}
        persona.version = 1
        persona.lead_client_id = "lc-1"

        candidates = [
            ExtractedFact("full_name", "Дмитрий", 0.95, "зовут Дмитрий"),
            ExtractedFact("city", "Москва", 0.90, "из Москвы"),
        ]

        # First call raises PersonaConflict, second succeeds
        async def _flaky_lock_slot(db, **kwargs):
            if kwargs["slot_code"] == "full_name":
                raise persona_memory.PersonaConflict(
                    expected=1, actual=2, lead_client_id="lc-1",
                )
            return (persona, MagicMock())

        with patch(
            "app.services.persona_fact_extractor.extract_facts_from_turn",
            AsyncMock(return_value=candidates),
        ), patch(
            "app.services.persona_memory.lock_slot", side_effect=_flaky_lock_slot,
        ):
            n = await extract_and_commit_facts_for_turn(
                db=MagicMock(),
                session_id="sid",
                user_id="uid",
                manager_message="зовут Дмитрий, из Москвы",
                persona=persona,
            )
        # First failed, second committed.
        assert n == 1

    @pytest.mark.asyncio
    async def test_extractor_exception_returns_zero(self):
        from app.services.persona_fact_extractor import (
            extract_and_commit_facts_for_turn,
        )

        persona = MagicMock()
        persona.confirmed_facts = {}
        persona.version = 1

        with patch(
            "app.services.persona_fact_extractor.extract_facts_from_turn",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            n = await extract_and_commit_facts_for_turn(
                db=MagicMock(),
                session_id="sid",
                user_id="uid",
                manager_message="меня зовут Иван",
                persona=persona,
            )
        assert n == 0
