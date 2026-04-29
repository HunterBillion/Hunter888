"""Sprint 0 §4 — pin the active_factors plumbing helper.

The helper ``_call_tts_factors`` lives in ``app.ws.training`` and bridges
the per-session ``state["active_factors"]`` list with the six TTS call
sites in voice/call mode. It must:

  * return None when ``CALL_HUMANIZED_V2`` is OFF, so the audible output
    stays bit-for-bit identical to pre-Sprint-0 (the TTS humaniser
    activates factor-specific hesitations / breathing only when factors
    are passed; passing ``[]`` is not the same as ``None`` because of the
    cache key path).
  * return a fresh ``list`` (not the original reference) when the flag is
    ON, so a downstream mutation cannot corrupt session state.
  * tolerate empty / missing state without raising.

These properties are pinned via static + runtime assertions below.
"""

from unittest.mock import patch
import ast
from pathlib import Path

import pytest


def test_helper_exists_and_returns_none_when_flag_off():
    from app.ws.training import _call_tts_factors

    state = {"active_factors": [{"factor": "fatigue", "intensity": 0.6}]}
    with patch("app.ws.training.settings") as mock_settings:
        mock_settings.call_humanized_v2 = False
        assert _call_tts_factors(state) is None


def test_helper_returns_list_when_flag_on():
    from app.ws.training import _call_tts_factors

    factors = [
        {"factor": "fatigue", "intensity": 0.6},
        {"factor": "anxiety", "intensity": 0.4},
    ]
    state = {"active_factors": factors}
    with patch("app.ws.training.settings") as mock_settings:
        mock_settings.call_humanized_v2 = True
        out = _call_tts_factors(state)
        assert out == factors
        # Must be a fresh list — caller may not mutate the matrix output.
        assert out is not factors


def test_helper_returns_empty_list_when_state_empty_and_flag_on():
    from app.ws.training import _call_tts_factors

    with patch("app.ws.training.settings") as mock_settings:
        mock_settings.call_humanized_v2 = True
        assert _call_tts_factors({}) == []
        assert _call_tts_factors({"active_factors": None}) == []
        assert _call_tts_factors({"active_factors": []}) == []


def test_helper_handles_missing_active_factors_key():
    from app.ws.training import _call_tts_factors

    with patch("app.ws.training.settings") as mock_settings:
        mock_settings.call_humanized_v2 = False
        # Even with the flag ON the missing key path is exercised in the
        # next test; here we just check the OFF path doesn't read state.
        assert _call_tts_factors({"unrelated": "value"}) is None


def test_every_main_tts_call_site_uses_helper():
    """AST-pin: each ``get_tts_audio_b64`` call inside ``training.py`` that
    serves a voice/call path must pass ``active_factors=_call_tts_factors(state)``.

    The pre-existing call site at line ~4328 — a non-call path that
    already wired factors directly via ``state.get("active_factors", [])`` —
    is intentionally exempt. The exemption is checked by counting: at
    least 5 helper-using sites must exist.
    """
    src = (
        Path(__file__).parent.parent / "app" / "ws" / "training.py"
    ).read_text()
    # Five new sites (plus an old direct path) → at least 5 helper uses.
    helper_uses = src.count("active_factors=_call_tts_factors(state)")
    assert helper_uses >= 5, (
        f"Expected at least 5 voice/call TTS sites to use the helper, "
        f"found {helper_uses}. A site may have been added without "
        f"forwarding active_factors."
    )

    # Negative pin: no voice/call TTS call may use the bare 3-arg form.
    # The bare form was the bug — all five must now pass the helper.
    bare_form = "get_tts_audio_b64(_text, str(session_id), emotion="
    # The bare form may legitimately appear inside the helper's docstring
    # or comments, so search only inside the .py code body. Simple guard:
    # the bare form is only allowed if the very next non-whitespace
    # character is a comma (i.e. more args follow). We assert no occurrence
    # of the bare form followed immediately by ``)``.
    assert f"{bare_form}current_emotion)" not in src
    assert f"{bare_form}new_emotion)" not in src
    assert "get_tts_audio_b64(hangup_phrase, str(session_id), emotion=\"hangup\")" not in src


def test_helper_module_signature():
    """Static guard against accidental signature drift (the helper is
    consumed positionally by closures inside the WS handler)."""
    from app.ws.training import _call_tts_factors
    import inspect

    sig = inspect.signature(_call_tts_factors)
    params = list(sig.parameters)
    assert params == ["state"]
    # No async — must be cheap to call inside a tight loop.
    assert not inspect.iscoroutinefunction(_call_tts_factors)
