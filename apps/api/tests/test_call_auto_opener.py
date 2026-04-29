"""Sprint 0 §6 (Bug B fix) — auto-opener phrase contract.

Pin the small public surface of the opener feature: phrase pool stays
short and emotion-neutral, the picker always returns something from the
pool, and the gate behaviour is documented at the AST level (the live
WS handler is hard to unit-test without a full session bring-up, so we
pin its decision logic statically).
"""

from app.ws.training import CALL_AUTO_OPENERS, _pick_call_auto_opener


def test_opener_pool_is_nonempty_and_short():
    """Pool must have at least 3 variants so users don't hear the same
    word every session, and at most 8 so we don't sprawl into a content
    library — that is Sprint 1 territory (voice fingerprints)."""
    assert 3 <= len(CALL_AUTO_OPENERS) <= 8


def test_opener_pool_phrases_are_short():
    """Each phrase must be short enough to feel like a phone pick-up,
    not a monologue. 25 chars is the upper bound — 'Алло, кто это?' fits."""
    for phrase in CALL_AUTO_OPENERS:
        assert 1 <= len(phrase) <= 25, f"Opener too long: {phrase!r}"


def test_opener_pool_does_not_contain_ai_tells():
    """The opener cannot itself contain an AI-tell phrase, otherwise
    Sprint 0 §5 would scrub our greeting before TTS."""
    from app.services.ai_lexicon import KNOWN_RUSSIAN_AI_PHRASES
    for phrase in CALL_AUTO_OPENERS:
        normalized = phrase.lower()
        for tell in KNOWN_RUSSIAN_AI_PHRASES:
            assert tell not in normalized, (
                f"Opener {phrase!r} contains AI-tell {tell!r} — would be "
                f"scrubbed by Sprint 0 §5 gate before reaching TTS."
            )


def test_picker_returns_pool_member():
    """The picker must always return a phrase from the canonical pool —
    no on-the-fly synthesis, no LLM round-trip (would add latency to
    session start, defeating the point of having a pre-seeded opener)."""
    seen: set[str] = set()
    for _ in range(50):
        out = _pick_call_auto_opener()
        assert out in CALL_AUTO_OPENERS
        seen.add(out)
    # Should hit at least 2 different variants in 50 picks.
    assert len(seen) >= 2


def test_picker_returns_non_empty_string():
    out = _pick_call_auto_opener()
    assert isinstance(out, str) and out.strip()


def test_opener_helper_is_async_and_takes_three_args():
    """_send_call_auto_opener is the seam called by _handle_session_start.
    Pin its signature so future refactors don't silently break the
    session.started → opener flow."""
    from app.ws.training import _send_call_auto_opener
    import inspect

    sig = inspect.signature(_send_call_auto_opener)
    params = list(sig.parameters)
    assert params == ["ws", "session_id", "state"]
    assert inspect.iscoroutinefunction(_send_call_auto_opener)


def test_handler_gates_opener_on_three_flags():
    """AST guard: the session-start handler must check ALL THREE
    conditions (master flag + feature flag + session_mode in call/center)
    before sending the opener. Removing any one of them would either
    break opt-out (manager can't disable for a problematic env) or fire
    in chat mode (silent design contract)."""
    from pathlib import Path

    src = (
        Path(__file__).parent.parent / "app" / "ws" / "training.py"
    ).read_text()

    # Look for the eligibility expression composition. We do not parse
    # the AST node by node — a substring assertion is enough because the
    # three names co-occur in a single block by design.
    block_start = src.find("_opener_eligible")
    assert block_start > 0, "Opener gate block missing"
    block = src[block_start:block_start + 500]
    assert "settings.call_humanized_v2" in block
    assert "settings.call_humanized_v2_auto_opener" in block
    assert '"call"' in block and '"center"' in block
