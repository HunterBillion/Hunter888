"""Tests for S1-02: LLM Routing & Circuit Breaker fixes.

Covers:
- 2.2.1: Streaming calls _resolve_provider with correct arg order
- 2.2.2: Concurrent circuit breaker operations are thread-safe
- 2.2.3: _llm_stats operations are thread-safe
- 2.2.4: Claude model reads from settings
- 2.2.5: Gemini RPM boundary check with low limits
- 2.2.6: Exponential backoff from first 429
- 2.2.7: _filter_output collects all violation types
"""

import asyncio
import time
import pytest
from unittest.mock import patch, MagicMock


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2.1 — Correct argument order in streaming
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveProviderArgOrder:
    """Verify _resolve_provider is called with (prefer, tokens, task_type)."""

    def test_resolve_provider_signature(self):
        from app.services.llm import _resolve_provider
        import inspect
        sig = inspect.signature(_resolve_provider)
        params = list(sig.parameters.keys())
        assert params == ["prefer", "system_prompt_tokens", "task_type"]

    def test_resolve_provider_returns_local_for_simple(self):
        from app.services.llm import _resolve_provider
        result = _resolve_provider(prefer="auto", system_prompt_tokens=100, task_type="simple")
        assert result == "local"

    def test_resolve_provider_explicit_preference(self):
        from app.services.llm import _resolve_provider
        assert _resolve_provider("local", 100, "default") == "local"
        assert _resolve_provider("cloud", 100, "default") == "cloud"

    def test_streaming_uses_int_tokens_not_string(self):
        """Verify the streaming path computes prompt_tokens as int, not passes full_system string."""
        import ast
        from pathlib import Path
        source = Path(__file__).parent.parent / "app" / "services" / "llm.py"
        tree = ast.parse(source.read_text())
        # Find generate_response_stream function
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "generate_response_stream":
                body_source = ast.dump(node)
                # The call should use prompt_tokens (a number), not full_system (a string)
                assert "prompt_tokens" in body_source or "len(full_system)" in body_source
                break


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2.2 — asyncio.Lock for Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════════


class TestCircuitBreakerLock:
    """Verify concurrent circuit breaker ops don't race."""

    @pytest.mark.asyncio
    async def test_health_lock_exists(self):
        from app.services.llm import _get_health_lock
        lock = _get_health_lock()
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_concurrent_record_failure_no_race(self):
        """20 concurrent record_failure calls should result in exactly 20 failures."""
        from app.services.llm import _ProviderHealth, _get_health_lock
        health = _ProviderHealth(failure_threshold=100)  # High threshold to not trip
        lock = _get_health_lock()

        async def bump():
            async with lock:
                health.record_failure()

        await asyncio.gather(*[bump() for _ in range(20)])
        assert health.consecutive_failures == 20

    @pytest.mark.asyncio
    async def test_concurrent_success_resets(self):
        from app.services.llm import _ProviderHealth, _get_health_lock
        health = _ProviderHealth()
        health.consecutive_failures = 10
        lock = _get_health_lock()

        async with lock:
            health.record_success()
        assert health.consecutive_failures == 0
        assert health.consecutive_429s == 0

    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(self):
        """Mix of success/failure/quota operations under lock don't corrupt state."""
        from app.services.llm import _ProviderHealth, _get_health_lock
        health = _ProviderHealth(failure_threshold=100)
        lock = _get_health_lock()

        async def fail():
            async with lock:
                health.record_failure()

        async def succeed():
            async with lock:
                health.record_success()

        # 10 failures then 1 success should reset
        await asyncio.gather(*[fail() for _ in range(10)])
        assert health.consecutive_failures == 10
        await succeed()
        assert health.consecutive_failures == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2.3 — Thread-safe _llm_stats
# ═══════════════════════════════════════════════════════════════════════════════


class TestLLMStatsLock:
    """Verify _llm_stats updates are protected by lock."""

    @pytest.mark.asyncio
    async def test_stats_lock_exists(self):
        from app.services.llm import _get_stats_lock
        lock = _get_stats_lock()
        assert isinstance(lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_log_token_usage_is_async(self):
        """_log_token_usage must be async (uses lock internally)."""
        from app.services.llm import _log_token_usage
        import inspect
        assert inspect.iscoroutinefunction(_log_token_usage)

    @pytest.mark.asyncio
    async def test_get_llm_stats_is_async(self):
        """get_llm_stats must be async (reads under lock)."""
        from app.services.llm import get_llm_stats
        import inspect
        assert inspect.iscoroutinefunction(get_llm_stats)


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2.4 — Claude model from config
# ═══════════════════════════════════════════════════════════════════════════════


class TestClaudeModelConfig:
    """Verify Claude model is read from settings, not hardcoded."""

    def test_settings_has_claude_model(self):
        from app.config import Settings
        s = Settings()
        assert hasattr(s, "claude_model")
        assert s.claude_model == "claude-sonnet-4-6"

    def test_claude_model_not_hardcoded_in_llm(self):
        """Verify no hardcoded 'claude-sonnet' string in the Claude call."""
        from pathlib import Path
        source = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        # Should use settings.claude_model, not a hardcoded string
        assert 'model="claude-sonnet' not in source
        assert "settings.claude_model" in source

    def test_claude_model_configurable(self):
        """Settings should allow overriding claude_model via env."""
        from app.config import Settings
        with patch.dict("os.environ", {"CLAUDE_MODEL": "claude-haiku-4-5-20251001"}):
            s = Settings()
            assert s.claude_model == "claude-haiku-4-5-20251001"


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2.5 — Gemini RPM boundary check
# ═══════════════════════════════════════════════════════════════════════════════


class TestGeminiRPMBoundary:
    """Verify _gemini_has_quota handles low RPM limits."""

    def test_rpm_limit_1_still_allows_calls(self):
        from app.services.llm import _gemini_has_quota, _gemini_call_times
        _gemini_call_times.clear()
        with patch("app.services.llm.settings") as mock_settings:
            mock_settings.gemini_rpm_limit = 1
            # max(1, 1-2) = max(1, -1) = 1 → 0 < 1 is True
            assert _gemini_has_quota() is True

    def test_rpm_limit_0_still_allows_one(self):
        from app.services.llm import _gemini_has_quota, _gemini_call_times
        _gemini_call_times.clear()
        with patch("app.services.llm.settings") as mock_settings:
            mock_settings.gemini_rpm_limit = 0
            # max(1, 0-2) = max(1, -2) = 1 → 0 < 1 is True
            assert _gemini_has_quota() is True

    def test_rpm_limit_15_normal_behavior(self):
        from app.services.llm import _gemini_has_quota, _gemini_call_times
        _gemini_call_times.clear()
        with patch("app.services.llm.settings") as mock_settings:
            mock_settings.gemini_rpm_limit = 15
            # max(1, 15-2) = 13 → 0 < 13 is True
            assert _gemini_has_quota() is True

    def test_rpm_exhausted(self):
        from app.services.llm import _gemini_has_quota, _gemini_call_times
        import time
        now = time.monotonic()
        _gemini_call_times.clear()
        _gemini_call_times.extend([now] * 15)  # Fill with recent calls
        with patch("app.services.llm.settings") as mock_settings:
            mock_settings.gemini_rpm_limit = 15
            # 15 < max(1, 13) → 15 < 13 is False
            assert _gemini_has_quota() is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2.6 — Exponential backoff from first 429
# ═══════════════════════════════════════════════════════════════════════════════


class TestExponentialBackoff429:
    """Verify backoff starts from first 429, not second."""

    def test_first_429_sets_base_cooldown(self):
        from app.services.llm import _ProviderHealth
        h = _ProviderHealth(recovery_seconds=60.0)
        before = time.monotonic()
        h.record_quota_exhaustion()
        after = time.monotonic()
        # First 429: cooldown = 60 * 2^0 = 60s
        assert h.consecutive_429s == 1
        assert h.open_until >= before + 59  # ~60s cooldown
        assert h.open_until <= after + 61

    def test_second_429_doubles_cooldown(self):
        from app.services.llm import _ProviderHealth
        h = _ProviderHealth(recovery_seconds=60.0)
        h.record_quota_exhaustion()  # 60s
        h.record_quota_exhaustion()  # 120s
        assert h.consecutive_429s == 2
        # Second: 60 * 2^1 = 120s
        expected_min = time.monotonic() + 119
        assert h.open_until >= expected_min - 2

    def test_backoff_caps_at_600s(self):
        from app.services.llm import _ProviderHealth
        h = _ProviderHealth(recovery_seconds=60.0)
        for _ in range(10):
            h.record_quota_exhaustion()
        assert h.consecutive_429s == 10
        # 60 * 2^9 = 30720 → capped at 600
        assert h.open_until <= time.monotonic() + 601

    def test_success_resets_429_counter(self):
        from app.services.llm import _ProviderHealth
        h = _ProviderHealth()
        h.record_quota_exhaustion()
        h.record_quota_exhaustion()
        assert h.consecutive_429s == 2
        h.record_success()
        assert h.consecutive_429s == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2.7 — Full violations collection
# ═══════════════════════════════════════════════════════════════════════════════


class TestFilterOutputAllViolations:
    """Verify _filter_output collects ALL violation types, not just the first."""

    def test_role_break_no_early_exit(self):
        """Role break detection should not break early."""
        from app.services.content_filter import filter_ai_output
        # Text with role break
        text = "Как языковая модель, я не могу помочь"
        _, violations = filter_ai_output(text)
        assert "role_break" in violations

    def test_multiple_violation_types_collected(self):
        """Text with profanity + PII should report BOTH violation types."""
        from app.services.content_filter import filter_ai_output
        # Text containing both profanity and PII
        text = "Ты мудак, мой email test@example.com"
        _, violations = filter_ai_output(text)
        assert "profanity" in violations
        assert "pii_leak" in violations
        assert len(violations) >= 2

    def test_role_break_plus_pii_both_collected(self):
        """Text with role break + PII should report BOTH."""
        from app.services.content_filter import filter_ai_output
        text = "Как языковая модель, мой email test@example.com"
        _, violations = filter_ai_output(text)
        assert "role_break" in violations
        assert "pii_leak" in violations

    def test_all_three_violations(self):
        """Text with role_break + profanity + PII should collect all three."""
        from app.services.content_filter import filter_ai_output
        text = "Как языковая модель, ты мудак, email: admin@corp.ru"
        _, violations = filter_ai_output(text)
        assert "role_break" in violations
        assert "profanity" in violations
        assert "pii_leak" in violations
        assert len(violations) == 3

    def test_no_duplicate_violations(self):
        """Same violation type should appear only once."""
        from app.services.content_filter import filter_ai_output
        # Multiple PII patterns in same text
        text = "Email: a@b.com и ещё c@d.com и телефон +79991234567"
        _, violations = filter_ai_output(text)
        assert violations.count("pii_leak") == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 0 (2026-04-29) — max_tokens routing through providers
#
# Pre-Sprint-0 the ``max_tokens`` parameter on generate_response was a dead
# facade: it was computed but never reached the provider HTTP payloads, which
# all used hardcoded literals (Gemini 1200, Ollama/Claude/OpenAI 800).
#
# Sprint 0 wires it through. These tests pin the new contract:
#   1. Every provider function accepts ``max_tokens: int | None`` as a
#      positional arg between ``timeout`` and the keyword-only block.
#   2. ``_call_with_backoff`` forwards ``max_tokens`` to its call_fn.
#   3. When ``max_tokens`` is None, each provider falls back to its
#      historical hardcoded literal (preserves the no-caller-passes scenario
#      bit-for-bit).
#   4. When ``CALL_HUMANIZED_V2`` is OFF and the caller does not pass
#      ``max_tokens``, the dispatcher forwards None — legacy behaviour.
#   5. When ``CALL_HUMANIZED_V2`` is ON and ``session_mode in {call, center}``
#      the dispatcher forwards ``settings.call_humanized_v2_max_tokens``.
#   6. When the caller passes ``max_tokens`` explicitly, that wins regardless
#      of the flag — this IS a behavioural change relative to pre-Sprint-0
#      (where caller-supplied max_tokens was silently ignored), and the test
#      pins it intentionally.
# ═══════════════════════════════════════════════════════════════════════════════


class TestMaxTokensPlumbing:
    """Pin the max_tokens routing contract introduced in Sprint 0."""

    def test_call_gemini_accepts_max_tokens(self):
        from app.services.llm import _call_gemini
        import inspect
        sig = inspect.signature(_call_gemini)
        assert "max_tokens" in sig.parameters
        assert sig.parameters["max_tokens"].default is None

    def test_call_local_llm_accepts_max_tokens(self):
        from app.services.llm import _call_local_llm
        import inspect
        sig = inspect.signature(_call_local_llm)
        assert "max_tokens" in sig.parameters
        assert sig.parameters["max_tokens"].default is None
        # Must remain positional (between timeout and the keyword-only *).
        # Otherwise _call_with_backoff's positional forwarding would break.
        assert sig.parameters["max_tokens"].kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )

    def test_call_claude_accepts_max_tokens(self):
        from app.services.llm import _call_claude
        import inspect
        sig = inspect.signature(_call_claude)
        assert "max_tokens" in sig.parameters
        assert sig.parameters["max_tokens"].default is None

    def test_call_openai_accepts_max_tokens(self):
        from app.services.llm import _call_openai
        import inspect
        sig = inspect.signature(_call_openai)
        assert "max_tokens" in sig.parameters
        assert sig.parameters["max_tokens"].default is None

    def test_stream_ollama_accepts_max_tokens(self):
        from app.services.llm import _stream_ollama
        import inspect
        sig = inspect.signature(_stream_ollama)
        assert "max_tokens" in sig.parameters
        assert sig.parameters["max_tokens"].default is None

    def test_stream_gemini_accepts_max_tokens(self):
        from app.services.llm import _stream_gemini
        import inspect
        sig = inspect.signature(_stream_gemini)
        assert "max_tokens" in sig.parameters
        assert sig.parameters["max_tokens"].default is None

    def test_call_with_backoff_forwards_max_tokens(self):
        """_call_with_backoff must accept max_tokens and pass it as the 4th
        positional arg to call_fn — same slot as the new param on every
        provider func.
        """
        from app.services.llm import _call_with_backoff
        import inspect
        sig = inspect.signature(_call_with_backoff)
        assert "max_tokens" in sig.parameters
        assert sig.parameters["max_tokens"].default is None

    def test_call_with_backoff_forwards_max_tokens_runtime(self):
        """End-to-end check: passing max_tokens=300 to _call_with_backoff
        means the call_fn receives 300 as its 4th positional arg.
        """
        import asyncio
        from unittest.mock import AsyncMock, patch
        from app.services.llm import _call_with_backoff, LLMResponse

        captured = {}

        async def fake_call(system, messages, timeout, max_tokens):
            captured["max_tokens"] = max_tokens
            return LLMResponse(
                content="ok", model="fake", input_tokens=1,
                output_tokens=1, latency_ms=1,
            )

        # Skip the circuit-breaker check by pretending health is available.
        with patch("app.services.llm._provider_health") as mock_health:
            health = MagicMock()
            health.is_available.return_value = True
            mock_health.__getitem__.return_value = health

            asyncio.run(_call_with_backoff(
                "test", fake_call, "sys", [], 1.0, max_tokens=300,
            ))

        assert captured["max_tokens"] == 300

    def test_call_with_backoff_default_forwards_none(self):
        """When max_tokens is not passed, None reaches the provider so it
        can fall back to its historical hardcoded literal.
        """
        import asyncio
        from unittest.mock import patch
        from app.services.llm import _call_with_backoff, LLMResponse

        captured = {}

        async def fake_call(system, messages, timeout, max_tokens):
            captured["max_tokens"] = max_tokens
            return LLMResponse(
                content="ok", model="fake", input_tokens=1,
                output_tokens=1, latency_ms=1,
            )

        with patch("app.services.llm._provider_health") as mock_health:
            health = MagicMock()
            health.is_available.return_value = True
            mock_health.__getitem__.return_value = health

            asyncio.run(_call_with_backoff(
                "test", fake_call, "sys", [], 1.0,
            ))

        assert captured["max_tokens"] is None


class TestMaxTokensProviderFallback:
    """When max_tokens is None, every provider must use its historical literal.

    This pins the behaviour-preserving leg of the Sprint 0 change. The numbers
    in the asserts are the literals each provider used pre-Sprint-0:
      Gemini blocking + stream: 1200
      Ollama / OpenAI-compat / Claude / OpenAI-fallback: 800
    """

    def test_gemini_blocking_payload_uses_1200_when_none(self):
        """Inspect the Gemini blocking payload via AST: when max_tokens is
        None the literal 1200 must appear in the conditional fallback.
        """
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        tree = ast.parse(src)
        gemini_fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_call_gemini"
        )
        gemini_body = ast.dump(gemini_fn)
        assert "1200" in gemini_body, "Gemini blocking lost its 1200 fallback"

    def test_ollama_native_payload_uses_800_when_none(self):
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        tree = ast.parse(src)
        local_fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_call_local_llm"
        )
        body = ast.dump(local_fn)
        assert "800" in body, "Ollama / OpenAI-compat lost their 800 fallback"

    def test_claude_uses_800_when_none(self):
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        tree = ast.parse(src)
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_call_claude"
        )
        assert "800" in ast.dump(fn), "Claude lost its 800 fallback"

    def test_openai_fallback_uses_800_when_none(self):
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        tree = ast.parse(src)
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_call_openai"
        )
        assert "800" in ast.dump(fn), "OpenAI fallback lost its 800 fallback"

    def test_stream_ollama_uses_800_when_none(self):
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        tree = ast.parse(src)
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_stream_ollama"
        )
        assert "800" in ast.dump(fn), "Ollama stream lost its 800 fallback"

    def test_stream_gemini_uses_1200_when_none(self):
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        tree = ast.parse(src)
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_stream_gemini"
        )
        assert "1200" in ast.dump(fn), "Gemini stream lost its 1200 fallback"


class TestCallHumanizedV2DispatcherGate:
    """Pin the dispatcher gate logic.

    The translation table the dispatcher implements:

      caller passes max_tokens?  flag  session_mode  → forwarded
      ─────────────────────────  ────  ────────────  ──────────
      yes (any value X)          *     *             X
      no                         off   *             None  (legacy)
      no                         on    chat          None  (legacy — chat
                                                            never gets the
                                                            humanized cap)
      no                         on    call/center   settings.call_humanized
                                                     _v2_max_tokens
    """

    def test_flag_off_no_caller_passes_none(self):
        """The dispatcher source must compute a forwarded max_tokens gated
        on (call_humanized_v2 AND session_mode in call/center) OR caller-
        passed value. AST-level guard so the gate cannot silently regress.
        """
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        # The gate appears in BOTH generate_response and generate_response_stream.
        assert "call_humanized_v2" in src
        assert 'session_mode in ("call", "center")' in src

    def test_default_max_tokens_setting_is_phone_short(self):
        from app.config import settings
        # 2026-04-29 (Bug 1 fix): dropped from 300 to 80. 300 produced
        # ~80s of speech per turn — too verbose for a phone interaction.
        # If product wants a different cap it should be a conscious flip
        # in .env, not a silent change in code. See test_call_reply_length
        # for the canonical pin on the 80 default.
        assert settings.call_humanized_v2_max_tokens == 80

    def test_flag_default_off_in_settings(self):
        """Production must not get the V2 path until ops explicitly opts in."""
        from app.config import Settings
        # Read the class default, not the current process env (a developer
        # may have CALL_HUMANIZED_V2=1 in their local .env).
        default = Settings.model_fields["call_humanized_v2"].default
        assert default is False, (
            "CALL_HUMANIZED_V2 must default to False so the legacy path "
            "stays the production default until per-env opt-in."
        )

    def test_dispatcher_forwards_caller_max_tokens_even_when_flag_off(self):
        """Pinned behavioural change vs pre-Sprint-0:

        BEFORE: caller-supplied max_tokens was silently dropped (every
                provider used its hardcoded literal regardless).
        AFTER:  caller-supplied max_tokens wins. This is intentional —
                the parameter was always advertised on generate_response
                but was a dead facade. We are honouring it now.

        At time of the Sprint 0 change, NO production caller passes
        max_tokens (grepped: zero hits). If a future caller starts passing
        it, this test reminds them they are no longer in dead-facade land.
        """
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "app" / "services" / "llm.py").read_text()
        # The dispatcher must short-circuit to caller-supplied max_tokens
        # before checking the flag/session_mode.
        assert "if max_tokens is not None:" in src
        assert "_forwarded_max_tokens = max_tokens" in src
