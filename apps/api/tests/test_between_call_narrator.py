"""Tests for between_call_narrator.py — LLM-powered between-call intelligence."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import asdict

from app.services.between_call_narrator import (
    NarratorContext,
    NarratorResult,
    generate_between_call_content,
    generate_client_message_llm,
    generate_coaching_tips_llm,
    generate_coaching_tips_template,
    generate_emotional_forecast,
    generate_narrative_summary_llm,
    generate_suggested_opener_llm,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def basic_context():
    return NarratorContext(
        lifecycle_state="THINKING",
        relationship_score=55.0,
        call_number=2,
        total_calls=3,
        archetype_code="skeptic",
        client_name="Иванов Иван",
        last_outcome="considering",
        last_emotion="curious",
        last_score=65.0,
        key_memories=[
            {"content": "Клиент спрашивал про квартиру", "type": "fact", "salience": 8},
            {"content": "Менеджер обещал прислать документы", "type": "promise", "salience": 9},
        ],
        active_storylets=["wife_found_out"],
        manager_weak_points=["objection_handling", "closing"],
    )


@pytest.fixture
def hostile_context():
    return NarratorContext(
        lifecycle_state="REJECTED",
        relationship_score=20.0,
        call_number=3,
        total_calls=4,
        archetype_code="aggressive",
        client_name="Петров",
        last_outcome="hangup",
        last_emotion="hostile",
        last_score=30.0,
        active_storylets=["collectors_arrived"],
    )


@pytest.fixture
def first_call_context():
    return NarratorContext(
        lifecycle_state="FIRST_CONTACT",
        relationship_score=50.0,
        call_number=0,
        total_calls=3,
    )


@pytest.fixture
def mock_llm_response():
    """Mock LLMResponse object."""
    response = MagicMock()
    response.content = "Тестовый ответ от LLM"
    response.model = "gemini-test"
    response.input_tokens = 100
    response.output_tokens = 50
    response.latency_ms = 200
    return response


# ---------------------------------------------------------------------------
# NarratorContext tests
# ---------------------------------------------------------------------------

class TestNarratorContext:
    def test_defaults(self):
        ctx = NarratorContext()
        assert ctx.lifecycle_state == "FIRST_CONTACT"
        assert ctx.relationship_score == 50.0
        assert ctx.archetype_code == "skeptic"
        assert ctx.key_memories == []
        assert ctx.manager_weak_points == []

    def test_custom_values(self, basic_context):
        assert basic_context.lifecycle_state == "THINKING"
        assert basic_context.relationship_score == 55.0
        assert basic_context.archetype_code == "skeptic"
        assert len(basic_context.key_memories) == 2
        assert len(basic_context.active_storylets) == 1


# ---------------------------------------------------------------------------
# Emotional forecast tests
# ---------------------------------------------------------------------------

class TestEmotionalForecast:
    def test_hostile_low_trust(self, hostile_context):
        forecast = generate_emotional_forecast(hostile_context)
        assert forecast == "hostile"

    def test_hostile_high_trust(self):
        ctx = NarratorContext(
            last_emotion="hostile",
            relationship_score=60.0,
        )
        forecast = generate_emotional_forecast(ctx)
        assert forecast == "guarded"  # Recovery possible

    def test_curious_high_trust(self):
        ctx = NarratorContext(
            last_emotion="curious",
            relationship_score=70.0,
        )
        forecast = generate_emotional_forecast(ctx)
        assert forecast == "negotiating"

    def test_curious_low_trust(self):
        ctx = NarratorContext(
            last_emotion="curious",
            relationship_score=40.0,
        )
        forecast = generate_emotional_forecast(ctx)
        assert forecast == "curious"

    def test_deal_emotion(self):
        ctx = NarratorContext(last_emotion="deal")
        forecast = generate_emotional_forecast(ctx)
        assert forecast == "considering"

    def test_cold_default(self):
        ctx = NarratorContext(last_emotion="cold")
        forecast = generate_emotional_forecast(ctx)
        assert forecast == "guarded"

    def test_hangup(self):
        ctx = NarratorContext(last_emotion="hangup", relationship_score=10.0)
        forecast = generate_emotional_forecast(ctx)
        assert forecast == "hostile"


# ---------------------------------------------------------------------------
# Template coaching tips tests
# ---------------------------------------------------------------------------

class TestCoachingTipsTemplate:
    def test_hostile_emotion_advice(self, hostile_context):
        tips = generate_coaching_tips_template(hostile_context)
        assert len(tips) > 0
        assert any("враждебен" in t or "извинения" in t for t in tips)

    def test_cold_emotion_advice(self):
        ctx = NarratorContext(last_emotion="cold")
        tips = generate_coaching_tips_template(ctx)
        assert any("заинтересован" in t or "открытый вопрос" in t for t in tips)

    def test_low_trust_advice(self):
        ctx = NarratorContext(relationship_score=20.0)
        tips = generate_coaching_tips_template(ctx)
        assert any("Доверие" in t or "эмпатии" in t for t in tips)

    def test_high_trust_advice(self):
        ctx = NarratorContext(relationship_score=80.0, last_emotion="considering")
        tips = generate_coaching_tips_template(ctx)
        assert any("высокое" in t or "документов" in t or "конкретн" in t for t in tips)

    def test_weak_points_included(self, basic_context):
        tips = generate_coaching_tips_template(basic_context)
        assert len(tips) >= 2
        # Should include advice for objection_handling or closing
        combined = " ".join(tips)
        assert "возражения" in combined or "следующий шаг" in combined

    def test_storylet_wife_found_out(self):
        ctx = NarratorContext(active_storylets=["wife_found_out"], last_emotion="cold")
        tips = generate_coaching_tips_template(ctx)
        assert any("семейн" in t.lower() or "жена" in t.lower() for t in tips)

    def test_max_3_tips(self):
        ctx = NarratorContext(
            last_emotion="hostile",
            relationship_score=15.0,
            manager_weak_points=["objection_handling", "closing", "legal_knowledge"],
            active_storylets=["collectors_arrived"],
        )
        tips = generate_coaching_tips_template(ctx)
        assert len(tips) <= 3


# ---------------------------------------------------------------------------
# LLM generation tests (mocked)
# ---------------------------------------------------------------------------

class TestClientMessageLLM:
    @pytest.mark.asyncio
    async def test_generates_message(self, basic_context, mock_llm_response):
        mock_llm_response.content = "Здравствуйте, я подумал о нашем разговоре и хотел уточнить..."
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await generate_client_message_llm(basic_context)
            assert result is not None
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_strips_quotes(self, basic_context, mock_llm_response):
        mock_llm_response.content = '«Здравствуйте, хотел уточнить»'
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await generate_client_message_llm(basic_context)
            assert result is not None
            assert not result.startswith("«")
            assert not result.endswith("»")

    @pytest.mark.asyncio
    async def test_truncates_long_messages(self, basic_context, mock_llm_response):
        mock_llm_response.content = "А" * 600
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await generate_client_message_llm(basic_context)
            assert result is not None
            assert len(result) <= 500

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, basic_context):
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            side_effect=Exception("LLM down"),
        ):
            result = await generate_client_message_llm(basic_context)
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_response(self, basic_context, mock_llm_response):
        mock_llm_response.content = "   "
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await generate_client_message_llm(basic_context)
            assert result is None


class TestCoachingTipsLLM:
    @pytest.mark.asyncio
    async def test_parses_numbered_list(self, basic_context, mock_llm_response):
        mock_llm_response.content = (
            "1. Начните с вопроса о семейной ситуации клиента.\n"
            "2. Подготовьте конкретный расчёт стоимости процедуры.\n"
            "3. Используйте технику активного слушания.\n"
        )
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            tips = await generate_coaching_tips_llm(basic_context)
            assert tips is not None
            assert len(tips) == 3
            assert not any(t.startswith("1.") for t in tips)  # Numbers stripped

    @pytest.mark.asyncio
    async def test_skips_if_doing_well(self, mock_llm_response):
        ctx = NarratorContext(relationship_score=80.0, manager_weak_points=[])
        tips = await generate_coaching_tips_llm(ctx)
        assert tips == []  # No coaching needed

    @pytest.mark.asyncio
    async def test_max_3_tips(self, basic_context, mock_llm_response):
        mock_llm_response.content = "\n".join(f"{i}. Совет номер {i} для менеджера." for i in range(1, 8))
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            tips = await generate_coaching_tips_llm(basic_context)
            assert tips is not None
            assert len(tips) <= 3


class TestNarrativeSummaryLLM:
    @pytest.mark.asyncio
    async def test_generates_narrative(self, basic_context, mock_llm_response):
        basic_context.between_events = [
            {"description": "Клиент посетил другого юриста"},
        ]
        mock_llm_response.content = (
            "Иванов провёл бессонную ночь, обдумывая разговор с менеджером. "
            "Утром жена обнаружила письма от банка."
        )
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await generate_narrative_summary_llm(basic_context)
            assert result is not None
            assert "Иванов" in result

    @pytest.mark.asyncio
    async def test_returns_none_without_events(self):
        ctx = NarratorContext()  # No events, no storylets
        result = await generate_narrative_summary_llm(ctx)
        assert result is None


# ---------------------------------------------------------------------------
# Main orchestrator tests
# ---------------------------------------------------------------------------

class TestGenerateBetweenCallContent:
    @pytest.mark.asyncio
    async def test_first_call_returns_empty(self, first_call_context):
        result = await generate_between_call_content(first_call_context)
        assert result.source == "template"
        assert result.coaching_tips == []
        assert result.client_message is None

    @pytest.mark.asyncio
    async def test_falls_back_to_template_on_llm_failure(self, basic_context):
        """When LLM fails, template coaching tips should still work."""
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            side_effect=Exception("LLM down"),
        ):
            result = await generate_between_call_content(basic_context)
            # Template coaching should still produce tips
            assert len(result.coaching_tips) > 0
            assert result.emotional_forecast != ""

    @pytest.mark.asyncio
    async def test_full_llm_flow(self, basic_context, mock_llm_response):
        basic_context.between_events = [{"description": "Событие"}]

        call_count = 0

        async def mock_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            if call_count == 1:  # client message
                resp.content = "Здравствуйте, думаю о нашем разговоре."
            elif call_count == 2:  # coaching tips
                resp.content = "1. Совет первый для менеджера.\n2. Совет второй для менеджера."
            elif call_count == 3:  # narrative
                resp.content = "Клиент провёл тяжёлый день."
            elif call_count == 4:  # opener
                resp.content = "Добрый день, как ваши дела?"
            else:
                resp.content = "Текст."
            return resp

        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            side_effect=mock_generate,
        ):
            result = await generate_between_call_content(basic_context)
            assert result.client_message is not None
            assert len(result.coaching_tips) >= 1
            assert result.narrative_summary != ""
            assert result.suggested_opener != ""
            assert result.source == "llm"

    @pytest.mark.asyncio
    async def test_emotional_forecast_always_present(self, basic_context):
        with patch(
            "app.services.between_call_narrator.generate_response",
            new_callable=AsyncMock,
            side_effect=Exception("LLM down"),
        ):
            result = await generate_between_call_content(basic_context)
            assert result.emotional_forecast != ""
            assert result.emotional_forecast in (
                "cold", "guarded", "curious", "considering",
                "negotiating", "deal", "testing", "callback",
                "hostile", "hangup",
            )
