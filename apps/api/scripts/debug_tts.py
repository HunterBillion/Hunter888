#!/usr/bin/env python3
"""TTS Diagnostic — run inside the API container or with uv.

Usage (Docker):
    docker compose exec api python debug_tts.py

Usage (local with uv):
    cd apps/api && uv run python debug_tts.py

Usage (local direct):
    cd Hunter888-main/apps/api && python debug_tts.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

def ok(msg): print(f"    {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"    {RED}✗{RESET} {msg}")
def warn(msg): print(f"    {YELLOW}⚠{RESET} {msg}")


def main():
    print(f"\n{BOLD}{'=' * 60}")
    print("  Hunter888 TTS Diagnostic")
    print(f"{'=' * 60}{RESET}\n")

    # ── Step 1: Environment variables ──
    print(f"{BOLD}[1] Environment variables:{RESET}")
    env_key = os.environ.get("ELEVENLABS_API_KEY", "")
    env_ids = os.environ.get("ELEVENLABS_VOICE_IDS", "")
    env_model = os.environ.get("ELEVENLABS_MODEL", "")
    env_enabled = os.environ.get("ELEVENLABS_ENABLED", "")

    if env_key: ok(f"ELEVENLABS_API_KEY = {env_key[:8]}...{env_key[-4:]}")
    else: fail("ELEVENLABS_API_KEY not set in environment")

    if env_ids: ok(f"ELEVENLABS_VOICE_IDS = {env_ids[:40]}...")
    else: fail("ELEVENLABS_VOICE_IDS not set in environment")

    if env_model: ok(f"ELEVENLABS_MODEL = {env_model}")
    else: warn("ELEVENLABS_MODEL not set (will use default)")

    if env_enabled: ok(f"ELEVENLABS_ENABLED = {env_enabled}")
    else: fail("ELEVENLABS_ENABLED not set in environment")

    # ── Step 2: .env files ──
    print(f"\n{BOLD}[2] .env file search:{RESET}")
    cwd = os.getcwd()
    print(f"    CWD: {cwd}")

    search_paths = [
        os.path.join(cwd, ".env"),
        os.path.join(cwd, "..", "..", ".env"),
        "/app/.env",
    ]
    try:
        from app.config import _ENV_FILES
        print(f"    config.py resolved: {_ENV_FILES}")
    except ImportError:
        warn("Could not import _ENV_FILES from config")

    for p in search_paths:
        ap = os.path.abspath(p)
        exists = os.path.exists(ap)
        if exists: ok(f"{ap}")
        else: warn(f"{ap} — not found")

    # ── Step 3: Settings ──
    print(f"\n{BOLD}[3] Pydantic Settings (final values):{RESET}")
    try:
        from app.config import settings

        if settings.elevenlabs_api_key:
            ok(f"api_key = {settings.elevenlabs_api_key[:8]}...{settings.elevenlabs_api_key[-4:]}")
        else:
            fail("api_key = EMPTY — .env not loaded!")

        if settings.elevenlabs_voice_ids:
            ok(f"voice_ids = {settings.elevenlabs_voice_ids[:50]}")
        else:
            fail("voice_ids = EMPTY")

        voices = settings.elevenlabs_voice_list
        if voices:
            ok(f"voice_list = {len(voices)} voices: {voices}")
        else:
            fail("voice_list = EMPTY (parsed from voice_ids)")

        ok(f"model = {settings.elevenlabs_model}")

        if settings.elevenlabs_enabled:
            ok(f"enabled = True")
        else:
            fail(f"enabled = False — TTS is OFF!")

        ok(f"timeout = {settings.elevenlabs_timeout_seconds}s")

    except Exception as e:
        fail(f"Settings load FAILED: {e}")
        import traceback; traceback.print_exc()
        return

    # ── Step 4: is_configured check ──
    print(f"\n{BOLD}[4] TTS Service checks:{RESET}")
    try:
        from app.services.tts import _is_configured, is_tts_available

        configured = _is_configured()
        available = is_tts_available()

        if configured: ok(f"_is_configured() = True")
        else:
            fail(f"_is_configured() = False — THIS IS WHY TTS DOESN'T WORK")
            if not settings.elevenlabs_api_key: fail("  → api_key empty")
            if not settings.elevenlabs_voice_list: fail("  → voice_list empty")
            if not settings.elevenlabs_enabled: fail("  → enabled=False")
            print(f"\n{RED}Fix: check that .env is loaded correctly{RESET}")
            return

        if available: ok(f"is_tts_available() = True")
        else: fail(f"is_tts_available() = False")

    except Exception as e:
        fail(f"Import error: {e}")
        import traceback; traceback.print_exc()
        return

    # ── Step 5: Voice assignment ──
    print(f"\n{BOLD}[5] Voice assignment:{RESET}")
    try:
        from app.services.tts import pick_voice_for_session, get_session_voice, release_session_voice

        test_sid = "diag-test-session-001"
        voice = pick_voice_for_session(test_sid)
        ok(f"Assigned voice: {voice}")

        retrieved = get_session_voice(test_sid)
        if retrieved == voice:
            ok(f"Retrieved matches: {retrieved}")
        else:
            fail(f"MISMATCH! assigned={voice} retrieved={retrieved}")

        release_session_voice(test_sid)
        ok("Released successfully")

    except Exception as e:
        fail(f"Voice assignment failed: {e}")
        import traceback; traceback.print_exc()
        return

    # ── Step 6: API call ──
    print(f"\n{BOLD}[6] ElevenLabs API call:{RESET}")
    try:
        from app.services.tts import synthesize_speech

        voice_id = settings.elevenlabs_voice_list[0]
        test_text = "Здравствуйте. Расскажите о вашей ситуации."

        print(f"    Calling API with voice={voice_id}, model={settings.elevenlabs_model}...")
        print(f"    Text: '{test_text}' ({len(test_text)} chars)")

        result = asyncio.run(synthesize_speech(test_text, voice_id))

        ok(f"API call SUCCESS!")
        ok(f"Audio: {len(result.audio_bytes)} bytes, {result.format}")
        ok(f"Latency: {result.latency_ms}ms")
        ok(f"Cached: {result.cached}")
        ok(f"Characters billed: {result.characters_used}")

        # Save test file
        test_path = "/tmp/tts_diagnostic.mp3"
        with open(test_path, "wb") as f:
            f.write(result.audio_bytes)
        ok(f"Saved to {test_path}")

    except Exception as e:
        fail(f"API call FAILED: {e}")
        import traceback; traceback.print_exc()

        # Extra diagnostics for common errors
        err_str = str(e).lower()
        if "api key" in err_str or "401" in err_str:
            print(f"\n    {RED}→ API key is invalid. Get a new one at https://elevenlabs.io/app/settings/api-keys{RESET}")
        elif "quota" in err_str or "402" in err_str or "429" in err_str:
            print(f"\n    {RED}→ Quota exhausted. Check your ElevenLabs plan limits.{RESET}")
        elif "timeout" in err_str:
            print(f"\n    {RED}→ API timeout. Try increasing ELEVENLABS_TIMEOUT_SECONDS.{RESET}")
        elif "unavailable" in err_str or "connect" in err_str:
            print(f"\n    {RED}→ Cannot reach api.elevenlabs.io. Check network/firewall.{RESET}")
        return

    # ── Step 7: Full pipeline ──
    print(f"\n{BOLD}[7] Full pipeline (get_tts_audio_b64):{RESET}")
    try:
        from app.services.tts import get_tts_audio_b64, pick_voice_for_session, release_session_voice
        import base64

        test_sid = "diag-pipeline-test"
        pick_voice_for_session(test_sid)

        b64 = asyncio.run(get_tts_audio_b64("Алло, вы слышите меня?", test_sid))

        if b64:
            ok(f"Base64 output: {len(b64)} chars")
            # Verify it's valid base64
            decoded = base64.b64decode(b64)
            ok(f"Decoded: {len(decoded)} bytes")
            ok(f"Starts with: {decoded[:4].hex()} ({'MP3 header ✓' if decoded[:2] == b'\\xff\\xfb' or decoded[:3] == b'ID3' else 'Unknown format ⚠'})")
        else:
            fail("Returned None — check logs above")

        release_session_voice(test_sid)

    except Exception as e:
        fail(f"Pipeline failed: {e}")
        import traceback; traceback.print_exc()

    # ── Summary ──
    print(f"\n{BOLD}{'=' * 60}")
    print(f"  Diagnostic COMPLETE")
    print(f"{'=' * 60}{RESET}")
    print(f"\n  If all steps passed {GREEN}✓{RESET}, TTS is working on backend.")
    print(f"  Problem is then in WebSocket delivery or frontend playback.")
    print(f"  Check browser DevTools → Network → WS → look for 'tts.audio' messages.\n")


if __name__ == "__main__":
    main()
