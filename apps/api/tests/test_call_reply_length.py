"""User-first Bug 1: short-reply directive in call mode.

Pins:
  * settings default cap is 80 (the sweet spot from field testing —
    not 300 which produced ~80s of speech, not 30 which mid-cuts)
  * REPLY_LENGTH directive is appended to the system prompt for V2 +
    call/center; absent for chat or flag-off
  * The directive is appended in BOTH paths (generate_response_stream
    AND generate_response blocking fallback) — they must stay in sync
"""

import re
from pathlib import Path


_LLM_PATH = Path(__file__).parent.parent / "app" / "services" / "llm.py"


def test_default_max_tokens_is_80():
    from app.config import Settings
    default = Settings.model_fields["call_humanized_v2_max_tokens"].default
    assert default == 80, (
        f"Default max_tokens for call mode is {default}, expected 80. "
        f"If you raised it on purpose, update this test and document why."
    )


def test_reply_length_directive_in_stream_path():
    """generate_response_stream must append [REPLY_LENGTH] when V2 +
    call/center. Static AST-level check so we don't drift."""
    src = _LLM_PATH.read_text()
    # Find the streaming function block.
    m = re.search(
        r"async def generate_response_stream\([^)]*\)[^:]*:.*?(?=\nasync def |\Z)",
        src,
        re.DOTALL,
    )
    assert m, "generate_response_stream not found in llm.py"
    block = m.group(0)
    assert "[REPLY_LENGTH]" in block, (
        "Streaming path is missing the [REPLY_LENGTH] short-reply directive"
    )
    assert "settings.call_humanized_v2" in block
    # The directive must be gated on session_mode in call/center.
    assert 'session_mode in ("call", "center")' in block


def test_reply_length_directive_in_blocking_path():
    """generate_response (blocking fallback) must append the same
    directive. The two paths must stay in sync — otherwise streaming
    behaves differently from the fallback when streaming providers fail."""
    src = _LLM_PATH.read_text()
    m = re.search(
        r"async def generate_response\([^)]*\)[^:]*:.*?(?=\nasync def |\Z)",
        src,
        re.DOTALL,
    )
    assert m, "generate_response not found in llm.py"
    block = m.group(0)
    assert "[REPLY_LENGTH]" in block, (
        "Blocking path is missing the [REPLY_LENGTH] short-reply directive — "
        "if streaming falls back to blocking, replies would suddenly grow long"
    )


def test_reply_length_directive_text_is_actionable():
    """The directive itself must mention the actual constraints — short
    phrases + one counter-question instead of a long answer. If a
    contributor blanks the directive text, this test catches it."""
    src = _LLM_PATH.read_text()
    # Both paths use identical text; check the substring once.
    assert "1-2 короткими" in src or "1-2 коротких" in src
    assert "телефон" in src.lower()
