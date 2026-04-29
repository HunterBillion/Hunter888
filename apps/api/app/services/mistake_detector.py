"""Mistake Detector — rule-based real-time coaching for the manager.

P1 (2026-04-29): adds a non-LLM coaching layer that watches the manager's
turns and emits ``coaching.mistake`` WS events when one of five common
sales mistakes is detected.

Design intent
─────────────
- **Rule-based, no LLM.** Latency must stay under 1ms per call. The
  detector runs on every manager message; LLM calls would push this to
  hundreds of ms and starve the audio pipeline.
- **Additive.** No existing hot-path code is modified. The detector is a
  separate function called next to ``StageTracker.process_message`` and
  emits a brand-new WS event type. Skip the import → call → no behaviour
  change for sessions where the flag is off.
- **Stateful per session.** State lives in Redis under
  ``coaching:{session_id}`` with a TTL matching the session lifetime.
  Each rule keeps its own minimal counters (last_open_question_ts,
  rolling_words_60s, repeat_phrase_counts, ...).
- **Hint authoring.** Each rule produces a short Russian-language hint
  ready to surface as a toast or chip. UI presentation is deliberately
  out of scope for P1 — the WS payload is the contract; the panel
  redesign is P2.

Five rules shipped in P1
────────────────────────
1. ``monologue``        — manager turn longer than ``MONOLOGUE_THRESHOLD``
                          characters AND no question mark.
2. ``no_open_question`` — no open-ended manager question in
                          ``NO_QUESTION_WINDOW_S`` seconds (markers:
                          interrogatives + question mark).
3. ``early_pricing``    — pricing keywords appear before stage 4
                          ("presentation"). Discounts here are common
                          UX failure mode — manager pitches the price
                          before the client knows what they're buying.
4. ``repeated_argument`` — the same content fragment from the manager
                           appears ``REPEAT_THRESHOLD`` times in a row.
5. ``talk_ratio_high``  — manager-spoken char volume / total volume
                          over a rolling 60s window > ``TALK_RATIO_MAX``.

Severity levels
───────────────
- ``info``: noted, no warning needed (example: first 30 sec of monologue).
- ``warn``: notable; coach should consider intervening (default).
- ``alert``: pattern, not single occurrence; show prominently.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ── Thresholds (deliberately low-magic, easy to tune from one place) ────────

MONOLOGUE_THRESHOLD = 200          # chars in a single manager message
MONOLOGUE_THRESHOLD_ALERT = 350    # chars → alert severity

NO_QUESTION_WINDOW_S = 12          # seconds without an open-ended question
NO_QUESTION_MIN_TURNS = 3          # don't fire on turn 1 — give a beat

EARLY_PRICING_STAGE_FLOOR = 4      # presentation; below this is "early"

REPEAT_THRESHOLD = 3               # same fragment repeated this many times

TALK_RATIO_WINDOW_S = 60.0         # rolling window for talk ratio
TALK_RATIO_MAX = 0.7               # manager talk volume / total
TALK_RATIO_MIN_TOTAL_CHARS = 200   # don't fire if there's barely any data

# State TTL — refreshed on every write. Sessions rarely run >2h so 4h is safe.
STATE_TTL_SECONDS = 4 * 60 * 60


# ── Marker regexes ───────────────────────────────────────────────────────────

# Pricing keywords that, when said before stage=presentation, are a known
# UX antipattern: the manager pitches the price before the client knows
# what they are buying.
_PRICING_RE = re.compile(
    r"\b(цен[аыеу]|стоимост[ьи]|сколько\s+стоит|по\s+цене|за\s+\d+\s*(?:тысяч|т\.?\s*р\.?|руб|₽))\b",
    flags=re.IGNORECASE,
)

# Open-ended question markers. Either a Russian interrogative or a literal
# "?" anywhere in the message. Closed yes/no questions still pass — this
# detector deliberately doesn't try to distinguish open vs closed beyond
# a rough heuristic. The point is to catch "manager talked for 60s with
# zero question marks at all".
_INTERROGATIVE_RE = re.compile(
    r"\b(как|почему|зачем|что|когда|где|куда|откуда|расскажите|опишите|поделитесь)\b",
    flags=re.IGNORECASE,
)


def _has_question(text: str) -> bool:
    if "?" in text:
        return True
    return bool(_INTERROGATIVE_RE.search(text))


def _normalise_phrase(text: str) -> str:
    """Lowercase + collapse whitespace for repeat-detection."""
    return " ".join(text.lower().split())


@dataclass
class Mistake:
    """Single detected mistake. Serialises to the ``coaching.mistake`` WS event."""

    type: str
    severity: str       # "info" | "warn" | "alert"
    hint: str           # short Russian hint for the manager
    detail: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "hint": self.hint,
            "detail": self.detail,
            "at": time.time(),
        }


@dataclass
class _CoachingState:
    """Per-session sliding state. Persisted to Redis as JSON."""

    last_open_question_ts: float = 0.0
    last_user_turn_ts: float = 0.0
    user_turn_count: int = 0
    # Rolling 60s window of (timestamp, manager_chars, ai_chars) tuples for talk-ratio.
    talk_window: list[tuple[float, int, int]] = field(default_factory=list)
    # Last 5 normalised manager phrases for repeat-detection.
    last_phrases: list[str] = field(default_factory=list)
    # De-dupe map: which mistake types have been emitted recently. Key →
    # last-emitted timestamp; we suppress re-emit within MIN_REEMIT_S.
    last_emitted: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_json(cls, raw: bytes | str | None) -> "_CoachingState":
        if not raw:
            return cls()
        try:
            d = json.loads(raw)
        except Exception:
            logger.debug("CoachingState: corrupt JSON, resetting")
            return cls()
        return cls(
            last_open_question_ts=float(d.get("last_open_question_ts", 0.0)),
            last_user_turn_ts=float(d.get("last_user_turn_ts", 0.0)),
            user_turn_count=int(d.get("user_turn_count", 0)),
            talk_window=[tuple(x) for x in d.get("talk_window", [])],  # type: ignore[misc]
            last_phrases=list(d.get("last_phrases", [])),
            last_emitted={k: float(v) for k, v in d.get("last_emitted", {}).items()},
        )

    def to_json(self) -> str:
        return json.dumps({
            "last_open_question_ts": self.last_open_question_ts,
            "last_user_turn_ts": self.last_user_turn_ts,
            "user_turn_count": self.user_turn_count,
            "talk_window": self.talk_window,
            "last_phrases": self.last_phrases,
            "last_emitted": self.last_emitted,
        })


# Suppress re-emit of the same mistake type within this many seconds. Avoids
# WS spam when the same condition keeps re-evaluating to True every turn.
MIN_REEMIT_S = 25.0


def _trim_window(window: list[tuple[float, int, int]], now: float) -> list[tuple[float, int, int]]:
    """Drop entries older than TALK_RATIO_WINDOW_S."""
    cutoff = now - TALK_RATIO_WINDOW_S
    return [t for t in window if t[0] >= cutoff]


# ── Pure-function detectors (no I/O) ─────────────────────────────────────────

def _detect_monologue(text: str) -> Mistake | None:
    if "?" in text:
        return None
    n = len(text)
    if n >= MONOLOGUE_THRESHOLD_ALERT:
        return Mistake(
            type="monologue",
            severity="alert",
            hint="ты говоришь сплошным монологом — задай вопрос клиенту",
            detail={"chars": n, "threshold": MONOLOGUE_THRESHOLD_ALERT},
        )
    if n >= MONOLOGUE_THRESHOLD:
        return Mistake(
            type="monologue",
            severity="warn",
            hint="реплика длинновата — разбей вопросом или паузой",
            detail={"chars": n, "threshold": MONOLOGUE_THRESHOLD},
        )
    return None


def _detect_no_open_question(state: _CoachingState, now: float) -> Mistake | None:
    if state.user_turn_count < NO_QUESTION_MIN_TURNS:
        return None
    if state.last_open_question_ts == 0.0:
        # Haven't seen any question in this session yet.
        return Mistake(
            type="no_open_question",
            severity="warn",
            hint="ты ещё не задал ни одного вопроса — открой клиента",
            detail={"turns_so_far": state.user_turn_count},
        )
    silence = now - state.last_open_question_ts
    if silence > NO_QUESTION_WINDOW_S:
        return Mistake(
            type="no_open_question",
            severity="warn",
            hint=f"уже {int(silence)} сек без вопросов — задай открытый",
            detail={"silence_seconds": int(silence)},
        )
    return None


def _detect_early_pricing(text: str, current_stage: int) -> Mistake | None:
    if current_stage >= EARLY_PRICING_STAGE_FLOOR:
        return None
    if not _PRICING_RE.search(text):
        return None
    return Mistake(
        type="early_pricing",
        severity="warn",
        hint="ты заговорил про цену до презентации — сначала ценность, потом стоимость",
        detail={"stage": current_stage, "stage_floor": EARLY_PRICING_STAGE_FLOOR},
    )


def _detect_repeated_argument(state: _CoachingState, text: str) -> Mistake | None:
    norm = _normalise_phrase(text)
    if len(norm) < 12:  # ignore short reactions ("да", "ага")
        return None
    state.last_phrases.append(norm)
    if len(state.last_phrases) > 5:
        state.last_phrases = state.last_phrases[-5:]
    # Consider near-duplicates: prefix overlap >= 80%.
    repeats = sum(
        1 for p in state.last_phrases if _phrase_similarity(p, norm) >= 0.8
    )
    if repeats >= REPEAT_THRESHOLD:
        return Mistake(
            type="repeated_argument",
            severity="alert",
            hint="ты повторяешь один и тот же аргумент — клиент не покупает, смени угол",
            detail={"repeats": repeats},
        )
    return None


def _phrase_similarity(a: str, b: str) -> float:
    """Cheap prefix-overlap similarity. Good enough for repeat detection."""
    if not a or not b:
        return 0.0
    short = min(len(a), len(b))
    long = max(len(a), len(b))
    common = 0
    for i in range(short):
        if a[i] != b[i]:
            break
        common += 1
    return common / long


def _detect_talk_ratio(state: _CoachingState, now: float) -> Mistake | None:
    window = _trim_window(state.talk_window, now)
    if not window:
        return None
    user_chars = sum(t[1] for t in window)
    ai_chars = sum(t[2] for t in window)
    total = user_chars + ai_chars
    if total < TALK_RATIO_MIN_TOTAL_CHARS:
        return None
    ratio = user_chars / total if total else 0.0
    if ratio <= TALK_RATIO_MAX:
        return None
    return Mistake(
        type="talk_ratio_high",
        severity="warn",
        hint=f"ты говоришь {int(ratio * 100)}% времени — дай клиенту высказаться",
        detail={"ratio": round(ratio, 2), "window_seconds": int(TALK_RATIO_WINDOW_S)},
    )


# ── Public API ───────────────────────────────────────────────────────────────

async def evaluate_user_turn(
    redis: Any,
    session_id: str,
    text: str,
    current_stage: int,
    *,
    now: float | None = None,
) -> list[Mistake]:
    """Process a manager (user) message, return any newly-fired mistakes.

    Side effects:
        Updates the per-session state in Redis (last_open_question_ts,
        last_phrases, talk_window, last_emitted, user_turn_count). Caller
        is responsible for emitting the returned ``Mistake`` objects via
        WebSocket as ``coaching.mistake`` events.
    """
    now = time.time() if now is None else now
    text = (text or "").strip()
    if not text:
        return []

    state = await _load_state(redis, session_id)
    state.user_turn_count += 1
    state.last_user_turn_ts = now

    # talk-ratio window: record manager char volume; ai_chars added in
    # ``record_assistant_turn``.
    state.talk_window = _trim_window(state.talk_window, now)
    state.talk_window.append((now, len(text), 0))

    # Update open-question marker before evaluating no_open_question.
    if _has_question(text):
        state.last_open_question_ts = now

    fired: list[Mistake] = []
    candidates: Iterable[Mistake | None] = (
        _detect_monologue(text),
        _detect_no_open_question(state, now),
        _detect_early_pricing(text, current_stage),
        _detect_repeated_argument(state, text),
        _detect_talk_ratio(state, now),
    )
    for c in candidates:
        if c is None:
            continue
        last = state.last_emitted.get(c.type, 0.0)
        if now - last < MIN_REEMIT_S:
            continue
        state.last_emitted[c.type] = now
        fired.append(c)

    await _save_state(redis, session_id, state)
    return fired


async def record_assistant_turn(
    redis: Any,
    session_id: str,
    text: str,
    *,
    now: float | None = None,
) -> None:
    """Record AI char volume into the talk-ratio window.

    No mistakes ever fire on AI turns — coaching is for the manager only.
    """
    now = time.time() if now is None else now
    text = (text or "").strip()
    if not text:
        return
    state = await _load_state(redis, session_id)
    state.talk_window = _trim_window(state.talk_window, now)
    state.talk_window.append((now, 0, len(text)))
    await _save_state(redis, session_id, state)


# ── Redis I/O ────────────────────────────────────────────────────────────────

def _key(session_id: str) -> str:
    return f"coaching:{session_id}"


async def _load_state(redis: Any, session_id: str) -> _CoachingState:
    if redis is None:
        return _CoachingState()
    try:
        raw = await redis.get(_key(session_id))
        return _CoachingState.from_json(raw)
    except Exception:
        logger.debug("coaching state load failed for %s", session_id, exc_info=True)
        return _CoachingState()


async def _save_state(redis: Any, session_id: str, state: _CoachingState) -> None:
    if redis is None:
        return
    try:
        await redis.set(_key(session_id), state.to_json(), ex=STATE_TTL_SECONDS)
    except Exception:
        logger.debug("coaching state save failed for %s", session_id, exc_info=True)


async def reset(redis: Any, session_id: str) -> None:
    """Clear per-session coaching state. Called on session.end."""
    if redis is None:
        return
    try:
        await redis.delete(_key(session_id))
    except Exception:
        logger.debug("coaching state reset failed for %s", session_id, exc_info=True)


__all__ = [
    "Mistake",
    "evaluate_user_turn",
    "record_assistant_turn",
    "reset",
    # exposed for tests
    "_CoachingState",
    "_detect_monologue",
    "_detect_no_open_question",
    "_detect_early_pricing",
    "_detect_repeated_argument",
    "_detect_talk_ratio",
]
