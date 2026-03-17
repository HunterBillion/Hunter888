"""Tests for LLM service: output filtering, fallback phrases, prompt loading."""

from app.services.llm import (
    FALLBACK_PHRASES,
    _filter_output,
    _build_system_prompt,
    _trim_history,
    load_prompt,
)


class TestOutputFiltering:
    def test_clean_text_passes(self):
        text = "Здравствуйте, расскажите о вашей ситуации."
        result, filtered = _filter_output(text)
        assert result == text
        assert filtered is False

    def test_profanity_caught(self):
        text = "Ну ты блядь, что делаешь"
        result, filtered = _filter_output(text)
        assert filtered is True
        assert result == FALLBACK_PHRASES[0]

    def test_role_break_caught(self):
        text = "Я языковая модель и не могу помочь"
        result, filtered = _filter_output(text)
        assert filtered is True
        assert result == FALLBACK_PHRASES[1]

    def test_pii_phone_redacted(self):
        text = "Позвоните мне на 123-456-7890"
        result, filtered = _filter_output(text)
        assert filtered is True
        assert "[СКРЫТО]" in result

    def test_pii_email_redacted(self):
        text = "Напишите на user@example.com"
        result, filtered = _filter_output(text)
        assert filtered is True
        assert "[СКРЫТО]" in result

    def test_pii_card_redacted(self):
        text = "Номер карты 1234 5678 9012 3456"
        result, filtered = _filter_output(text)
        assert filtered is True
        assert "[СКРЫТО]" in result

    def test_english_role_break(self):
        text = "I am an AI language model"
        result, filtered = _filter_output(text)
        assert filtered is True


class TestFallbackPhrases:
    def test_not_empty(self):
        assert len(FALLBACK_PHRASES) >= 3

    def test_all_strings(self):
        for phrase in FALLBACK_PHRASES:
            assert isinstance(phrase, str)
            assert len(phrase) > 0


class TestTrimHistory:
    def test_under_limit(self):
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        assert _trim_history(msgs, 10) == msgs

    def test_over_limit(self):
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(30)]
        result = _trim_history(msgs, 20)
        assert len(result) == 20
        assert result[0]["content"] == "msg 10"

    def test_exact_limit(self):
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        assert _trim_history(msgs, 20) == msgs


class TestBuildSystemPrompt:
    def test_combines_parts(self):
        result = _build_system_prompt("char prompt", "guardrails", "cold")
        assert "char prompt" in result
        assert "guardrails" in result
        assert "cold" in result

    def test_empty_character(self):
        result = _build_system_prompt("", "guardrails", "warming")
        assert "warming" in result

    def test_emotion_state_injected(self):
        result = _build_system_prompt("test", "", "open")
        assert "open" in result
