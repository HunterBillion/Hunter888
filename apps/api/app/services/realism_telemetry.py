"""Realism telemetry — snapshot which call-realism features were active.

The 2026-04-29..05-01 sweep introduced 8+ realism features
(Call Arc, IL-1 fillers, IL-2 ElevenLabs streaming, IL-3 STT priming,
persona-aware opener, RU PSTN ringback, phone-band TTS filter,
adaptive temperature, mistake detector). Each is independently flag-
gated. Without telemetry we cannot answer:

  * "What share of pilot sessions ran with phone-band ON?"
  * "Did adaptive_temperature correlate with higher completion rate?"
  * "Which opener phrase was used in the call where the trainee scored 95?"
  * "Are personas spending more time in hostile state since adaptive T flipped on?"

This module produces a small, structured snapshot of every realism
feature that's currently active. Caller persists it on the session
(``scoring_details["_realism"]``) and emits a ``DomainEvent`` of type
``call.realism_snapshot`` so the unified TZ-1 timeline picks it up.

Intentionally tiny — we record CONFIGURATION, not per-turn traces.
Per-turn traces (e.g. exact temperature used on turn 7) are the next
layer; without the configuration snapshot we can't even slice them.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def snapshot_realism_features(
    settings_obj: Any,
    *,
    session_mode: str = "chat",
) -> dict[str, Any]:
    """Build a flat dict of which realism features are active right now.

    Args:
        settings_obj: ``app.config.settings`` (passed in to keep this
            module testable without importing the live settings global).
        session_mode: "call" / "center" / "chat" — some features apply
            only to call mode; the snapshot still records the value
            but we tag ``call_eligible`` so analytics can distinguish
            "feature OFF" from "feature ON but irrelevant for this mode".

    Returns:
        ``dict`` keyed by short feature name → value. Always includes
        ``snapshot_version`` for forward compatibility.
    """
    is_call = session_mode in ("call", "center")

    # Read flags defensively — getattr() so older settings objects
    # without a flag don't crash analytics on resumed sessions.
    def _bool(name: str) -> bool:
        return bool(getattr(settings_obj, name, False))

    return {
        "snapshot_version": 1,
        "session_mode": session_mode,
        "call_eligible": is_call,
        # ── Call Arc (P0) ─────────────────────────────────────────────
        "call_arc_v1": _bool("call_arc_v1"),
        "call_arc_inject_reality": _bool("call_arc_inject_reality"),
        # ── IL-1 filler audio ────────────────────────────────────────
        "call_filler_v1": _bool("call_filler_v1"),
        # ── IL-2 ElevenLabs streaming ────────────────────────────────
        "elevenlabs_streaming_enabled": _bool("elevenlabs_streaming_enabled"),
        # ── IL-3 STT keyword priming ─────────────────────────────────
        "stt_keyword_prompt_enabled": _bool("stt_keyword_prompt_enabled"),
        # ── Persona-aware opener ─────────────────────────────────────
        "call_opener_persona_aware": _bool("call_opener_persona_aware"),
        # ── Adaptive temperature 0.4-1.0 ─────────────────────────────
        "adaptive_temperature_enabled": _bool("adaptive_temperature_enabled"),
        # ── Mistake detector (P1) ────────────────────────────────────
        "coaching_mistake_detector_v1": _bool("coaching_mistake_detector_v1"),
        # ── Call humanisation V2 (Sprint 0 master switch) ────────────
        "call_humanized_v2": _bool("call_humanized_v2"),
        "call_humanized_v2_max_tokens": int(
            getattr(settings_obj, "call_humanized_v2_max_tokens", 0) or 0,
        ),
        "call_humanized_v2_scrub_mode": str(
            getattr(settings_obj, "call_humanized_v2_scrub_mode", "warn") or "warn",
        ),
        "call_humanized_v2_auto_opener": _bool("call_humanized_v2_auto_opener"),
    }


def count_active_realism_features(snap: dict[str, Any]) -> int:
    """How many realism features are ON in this snapshot — quick scalar
    for dashboards / scoring details. Excludes meta keys (version, mode,
    eligibility, scalar config like max_tokens / scrub_mode)."""
    skip_keys = {
        "snapshot_version", "session_mode", "call_eligible",
        "call_humanized_v2_max_tokens", "call_humanized_v2_scrub_mode",
    }
    return sum(
        1 for k, v in snap.items()
        if k not in skip_keys and isinstance(v, bool) and v
    )


__all__ = ["snapshot_realism_features", "count_active_realism_features"]
