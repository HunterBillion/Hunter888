"""Tests for edge case constants and WebSocket protocol."""


class TestWSConstants:
    def test_silence_warning_sec(self):
        from app.ws.training import SILENCE_WARNING_SEC
        assert SILENCE_WARNING_SEC == 30

    def test_silence_timeout_sec(self):
        from app.ws.training import SILENCE_TIMEOUT_SEC
        assert SILENCE_TIMEOUT_SEC == 60

    def test_max_stt_failures(self):
        from app.ws.training import MAX_STT_FAILURES
        assert MAX_STT_FAILURES == 3

    def test_silence_timeout_greater_than_warning(self):
        from app.ws.training import SILENCE_TIMEOUT_SEC, SILENCE_WARNING_SEC
        assert SILENCE_TIMEOUT_SEC > SILENCE_WARNING_SEC


class TestSTTConstants:
    def test_stt_result_dataclass(self):
        from app.services.stt import STTResult
        result = STTResult(text="тест", confidence=0.9, language="ru", duration_ms=1000)
        assert result.text == "тест"
        assert result.confidence == 0.9
        assert result.language == "ru"
        assert result.duration_ms == 1000


class TestConfigValidation:
    def test_settings_have_embeddings_config(self):
        from app.config import Settings
        s = Settings()
        assert hasattr(s, "embeddings_service_url")
        assert hasattr(s, "gemini_embedding_api_key")

    def test_settings_have_llm_config(self):
        from app.config import Settings
        s = Settings()
        assert hasattr(s, "claude_api_key")
        assert hasattr(s, "openai_api_key")
        assert hasattr(s, "llm_primary_model")
        assert hasattr(s, "local_llm_url")
        assert hasattr(s, "local_llm_enabled")
        assert hasattr(s, "local_llm_api_key")

    def test_rate_limit_defaults(self):
        from app.config import Settings
        s = Settings()
        assert s.max_sessions_per_day == 10
        assert s.max_session_duration_minutes == 30
        assert s.max_messages_per_session == 200
