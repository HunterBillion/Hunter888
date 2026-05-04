"""Mode-switch detector — fires when manager pivots from off-task / trolling
back to a real, on-domain conversation.

Background (2026-05-03 prod incident, BUG 3)
--------------------------------------------
Test session: user trolled the cold-call bot for ~6 turns ("я курьер
пиццы", "комната Г-69", random typos), then switched to a real question
("у меня правда долг 800к, что делать?"). The existing mistake_detector
(5 fixed rules: monologue / no_open_question / early_pricing /
repeated_argument / talk_ratio_high) stayed silent. The user wanted
coaching to wake up and help on the pivot — exactly when a real
conversation begins.

Pattern adapted from Gong/Chorus public talks ("moment classifier +
advice generator", two stages). The original plan was an LLM-judge
overlay on Haiku, but for this specific symptom a deterministic keyword
classifier is enough: it adds zero latency, zero cost, and produces a
single actionable tip exactly when the user reaches for the steering
wheel after joking around. LLM-judge can be added on top later as a
second stage if the keyword approach proves too crude.

Detection rule
--------------
1. Maintain a rolling window of the last ``WINDOW_SIZE`` user turns +
   their classification (on_task / off_task / unknown).
2. ``off_task`` = no domain keyword AND (≤ 4 chars OR contains an
   off-domain marker like "пицца", "курьер", "иди", "ха-ха", emoji
   density > 30%, repeated punctuation).
3. ``on_task`` = contains at least one domain keyword (debt / bankruptcy
   / lawyer / court / contract / refinance / etc.).
4. **Mode switch fires** when the last ≥2 turns were ``off_task`` AND
   the current turn is ``on_task``. We emit at most once per session
   (re-arm requires an outcome reset; this is a coaching nudge, not
   a recurring siren).
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Final, Literal

logger = logging.getLogger(__name__)

# Keep the public type narrow — three values, no surprises.
TurnMode = Literal["on_task", "off_task", "unknown"]

WINDOW_SIZE: Final[int] = 6
MIN_OFF_TASK_BEFORE_SWITCH: Final[int] = 2
STATE_TTL_SECONDS: Final[int] = 4 * 60 * 60
REDIS_KEY_FMT: Final[str] = "coach_mode_switch:{session_id}"

# ── Domain vocabulary (cold-call simulator: debt / 127-ФЗ / bankruptcy) ─────
# Conservative — only words that are *clearly* about the call topic.
# Adding ambiguous words (e.g. "деньги") creates false-positive "on_task"
# matches when the user is still trolling about pizza prices.
_DOMAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"долг\w*|кредит\w*|займ\w*|ипотек\w*|алимент\w*|"
    r"банкрот\w*|127[\s\-]?фз|127\s*-?\s*фз|"
    r"коллектор\w*|приставы?|приставо\w*|"
    r"арбитражн\w*|суд[аеуы]?|судебн\w*|"
    r"списан\w*|реструктуриз\w*|рефинансир\w*|"
    r"имуществ\w*|залог\w*|ипотек\w*|"
    r"договор\w*|услуг\w*|стоимост\w*|оплат\w*|тариф\w*"
    r")\b",
    flags=re.IGNORECASE,
)

# Off-domain markers that strongly indicate trolling.
_OFF_DOMAIN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"пицц\w*|курьер\w*|шаурм\w*|роллы?|суши|"
    r"ха[\-\s]?ха|хех|лол|кек|ору|"
    r"идиот\w*|тупой|дурак|"
    r"шут\w*|прикол\w*"
    r")\b",
    flags=re.IGNORECASE,
)

_EMOJI_RE: Final[re.Pattern[str]] = re.compile(
    r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]"
)

_REPEATED_PUNCT_RE: Final[re.Pattern[str]] = re.compile(r"[?!.]{3,}|\)\)\)+|\(\(\(+")


def classify_turn(text: str) -> TurnMode:
    """Classify one manager utterance as on_task / off_task / unknown.

    Pure function — easy to unit-test. The thresholds are conservative
    by design: when in doubt, return ``unknown`` so the switch detector
    doesn't false-fire.
    """
    if not text:
        return "unknown"
    t = text.strip()
    if not t:
        return "unknown"

    has_domain = bool(_DOMAIN_RE.search(t))
    has_off_domain = bool(_OFF_DOMAIN_RE.search(t))

    # Domain word wins, even when off-domain markers also appear —
    # "ха-ха, у меня долг 500к" is the user reaching for the steering
    # wheel after a joke; classifying as on_task is exactly what triggers
    # the mode-switch tip the manager needs.
    if has_domain:
        return "on_task"

    # Strong off-domain signal.
    if has_off_domain:
        return "off_task"

    # Heuristics for "garbage / nonsense" without explicit off-domain word.
    char_count = len(t)
    emoji_count = len(_EMOJI_RE.findall(t))
    if char_count > 0 and (emoji_count / char_count) > 0.30:
        return "off_task"
    if _REPEATED_PUNCT_RE.search(t):
        return "off_task"
    # Very short non-domain (≤ 4 chars, no question, no domain word) — likely
    # noise / interjection, not an on-task move.
    if char_count <= 4 and "?" not in t:
        return "off_task"

    return "unknown"


@dataclass
class _SwitchState:
    """Per-session rolling state. Persisted to Redis as JSON."""

    window: list[TurnMode] = field(default_factory=list)
    fired_once: bool = False

    @classmethod
    def from_json(cls, raw: bytes | str | None) -> "_SwitchState":
        if not raw:
            return cls()
        try:
            d = json.loads(raw)
            return cls(
                window=[m for m in d.get("window", []) if m in ("on_task", "off_task", "unknown")],
                fired_once=bool(d.get("fired_once", False)),
            )
        except Exception:
            logger.debug("ModeSwitchState: corrupt JSON, resetting")
            return cls()

    def to_json(self) -> str:
        return json.dumps({"window": self.window, "fired_once": self.fired_once})


@dataclass
class ModeSwitchTip:
    """Coaching tip emitted on a detected pivot from trolling → on-task."""

    type: str = "mode_switch_to_on_task"
    severity: str = "info"
    hint: str = (
        "Пользователь только что перешёл от шуток к делу. "
        "Подхватите момент: задайте открытый вопрос о ситуации "
        "клиента, а не сразу предлагайте решение."
    )
    detail: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "hint": self.hint,
            "detail": self.detail,
            "at": time.time(),
        }


async def evaluate_mode_switch(
    redis_client: Any,
    session_id: str,
    user_text: str,
) -> ModeSwitchTip | None:
    """Update rolling state and return a tip iff a switch just happened.

    Same async signature as ``mistake_detector.evaluate_user_turn`` so it
    can sit beside it in the WS handler without changing the call shape.

    Fires at most once per session (``fired_once``). Re-firing on every
    pivot would teach managers to ignore the tip; one well-timed nudge
    is the entire UX value.
    """
    if not user_text:
        return None
    key = REDIS_KEY_FMT.format(session_id=session_id)

    raw = None
    try:
        raw = await redis_client.get(key)
    except Exception:
        logger.debug("ModeSwitch: redis read failed for %s", session_id, exc_info=True)
    state = _SwitchState.from_json(raw)

    current_mode = classify_turn(user_text)
    state.window.append(current_mode)
    if len(state.window) > WINDOW_SIZE:
        state.window = state.window[-WINDOW_SIZE:]

    tip: ModeSwitchTip | None = None
    if not state.fired_once and current_mode == "on_task" and len(state.window) >= 2:
        prior = state.window[:-1]
        off_task_in_prior = sum(1 for m in prior if m == "off_task")
        if off_task_in_prior >= MIN_OFF_TASK_BEFORE_SWITCH:
            tip = ModeSwitchTip(detail={
                "window": list(state.window),
                "off_task_count": off_task_in_prior,
            })
            state.fired_once = True
            logger.info(
                "Mode switch detected (session=%s): off_task=%d → on_task",
                session_id, off_task_in_prior,
            )

    try:
        await redis_client.setex(key, STATE_TTL_SECONDS, state.to_json())
    except Exception:
        logger.debug("ModeSwitch: redis write failed for %s", session_id, exc_info=True)

    return tip


__all__ = [
    "classify_turn",
    "evaluate_mode_switch",
    "ModeSwitchTip",
    "TurnMode",
    "WINDOW_SIZE",
    "MIN_OFF_TASK_BEFORE_SWITCH",
]
