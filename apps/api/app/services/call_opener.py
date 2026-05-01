"""IL-2026-05-01 — Persona-aware first-turn opener for the call mode.

Replaces the flat 5-phrase ``CALL_AUTO_OPENERS`` tuple with a register-
matched bank that picks the right Russian greeting based on the AI client's
mood + life stage. Drives directly off the sociolinguistic finding (cluster
1.4 of the deep research): Russian phone openers split into clear registers
that the listener immediately tags as «свой/чужой», «спокойный/раздражённый»,
«пожилой/молодой». A flat «Алло?» on every call is the strongest single
"this is AI" tell — every real call opens differently.

Register mapping
────────────────
The bank below is keyed by (mood, age_bucket). Mood comes from the persona's
starting emotion state; age_bucket from the generated profile (default
"middle" when unknown).

  mood        × age_bucket = phrase pool
  ──────────────────────────────────────
  hostile     × any          → «Что? / Ну? / Чего?»
  cold        × young        → «Да? / Слушаю.»
  cold        × middle       → «Алло. / Да, слушаю.»
  cold        × senior       → «Слушаю. / Да, слушаю вас.»
  guarded     × any          → «Да? / Алло, кто это?»
  curious     × any          → «Алло? / Да, слушаю.»
  considering × any          → «Да, слушаю. / Алло, говорите.»
  negotiating × any          → «Да, слушаю.»
  callback    × any          → «Слушаю. / Перезвоните позже?»
  testing     × any          → «Да? / Алло, кто это?»
  deal        × any          → «Да, слушаю вас.»
  hangup      × any          → ()  # no opener — about to hang up

Length is intentionally short (≤25 chars) — phone openers are reflex utterances,
not greetings. Anything longer reads as scripted.

Source for the register split: HiNative, NaTakallam, Sololingual on RU phone
greetings; Stivers et al. (PNAS 2009) on cross-linguistic opener turn-take
patterns.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

AgeBucket = Literal["young", "middle", "senior"]


def _age_to_bucket(age: int | None) -> AgeBucket:
    """Map raw age into a register bucket. None → middle (safe default)."""
    if age is None:
        return "middle"
    if age < 35:
        return "young"
    if age >= 50:
        return "senior"
    return "middle"


# (mood, age_bucket) → tuple of phrases. Lookup falls back: full key →
# (mood, "middle") → ("cold", age_bucket) → ("cold", "middle").
_OPENER_BANK: dict[tuple[str, AgeBucket], tuple[str, ...]] = {
    # Hostile — short, dismissive. Age doesn't matter much.
    ("hostile", "young"):  ("Что?", "Ну?", "Чего?"),
    ("hostile", "middle"): ("Что? Кто это?", "Ну?", "Чего надо?"),
    ("hostile", "senior"): ("Что? Кто это?", "Кто звонит?", "Чего вам?"),
    # Cold — neutral, register varies by age.
    ("cold", "young"):     ("Да?", "Слушаю.", "Алло?", "Да, слушаю."),
    ("cold", "middle"):    ("Алло.", "Да, слушаю.", "Слушаю.", "Алло, кто это?"),
    ("cold", "senior"):    ("Слушаю.", "Да, слушаю вас.", "Алло, кто говорит?", "Здравствуйте."),
    # Guarded — short, suspicious.
    ("guarded", "young"):  ("Да?", "Алло, кто это?"),
    ("guarded", "middle"): ("Алло, кто это?", "Да, слушаю.", "Кто звонит?"),
    ("guarded", "senior"): ("Слушаю. Кто это?", "Да, слушаю вас.", "Алло, кто говорит?"),
    # Curious — leaning in.
    ("curious", "young"):  ("Да, слушаю.", "Алло?"),
    ("curious", "middle"): ("Алло, слушаю.", "Да, слушаю вас.", "Алло?"),
    ("curious", "senior"): ("Да, слушаю вас.", "Алло, здравствуйте."),
    # Considering — measured.
    ("considering", "young"):  ("Да, слушаю.", "Алло?"),
    ("considering", "middle"): ("Да, слушаю вас.", "Алло, говорите."),
    ("considering", "senior"): ("Да, слушаю вас.", "Здравствуйте, слушаю."),
    # Negotiating — businesslike.
    ("negotiating", "young"):  ("Да, слушаю.",),
    ("negotiating", "middle"): ("Да, слушаю.", "Алло, говорите."),
    ("negotiating", "senior"): ("Да, слушаю вас.", "Здравствуйте."),
    # Callback — distracted, busy.
    ("callback", "young"):  ("Да? Минутку...", "Слушаю, говорите."),
    ("callback", "middle"): ("Да? Минутку.", "Слушаю, но кратко."),
    ("callback", "senior"): ("Да, слушаю.", "Минутку, я занят."),
    # Testing — challenging tone.
    ("testing", "young"):  ("Да? Кто это?", "Алло?"),
    ("testing", "middle"): ("Алло, кто это?", "Да, слушаю.", "Кто звонит?"),
    ("testing", "senior"): ("Алло, кто говорит?", "Слушаю.",),
    # Deal — engaged.
    ("deal", "young"):  ("Да, слушаю.",),
    ("deal", "middle"): ("Да, слушаю вас.",),
    ("deal", "senior"): ("Да, слушаю вас.", "Здравствуйте."),
}

DEFAULT_OPENER = "Алло?"


@dataclass(frozen=True)
class OpenerChoice:
    text: str
    emotion: str
    age_bucket: AgeBucket
    pickup_delay_ms: int  # 0-2000ms — caller plays this much silence before TTS


# Pickup-delay distribution per mood (cluster 1.5 — humans pick up 200-1800 ms
# after ring stops; "busy" personas wait longer, "expecting" personas pick up
# faster). Tuple = (min_ms, max_ms, mean_ms) for a clamped beta-like sample.
_PICKUP_DELAY_BY_MOOD: dict[str, tuple[int, int, int]] = {
    "hostile":      (200, 800,  400),   # short — ready to be annoyed
    "cold":         (300, 1500, 700),   # baseline neutral
    "guarded":      (400, 1400, 800),
    "curious":      (300, 1000, 600),
    "considering":  (400, 1300, 700),
    "negotiating":  (300, 1100, 600),
    "callback":     (800, 2000, 1300),  # long — busy, finding the phone
    "testing":      (500, 1500, 900),
    "deal":         (300, 1000, 500),
    "hangup":       (0,   0,    0),
}


def _sample_pickup_delay(emotion: str, rng: random.Random) -> int:
    band = _PICKUP_DELAY_BY_MOOD.get(emotion, _PICKUP_DELAY_BY_MOOD["cold"])
    lo, hi, mean = band
    if hi <= lo:
        return lo
    # Triangular distribution centred on mean — close enough to beta(2,5)
    # for our purposes, no numpy dep.
    return int(rng.triangular(lo, hi, mean))


def pick_opener(
    emotion: str,
    age: int | None = None,
    *,
    rng: random.Random | None = None,
) -> OpenerChoice:
    """Pick a register-matched opener phrase for the persona's mood + age.

    Falls back through (mood, "middle") → ("cold", age_bucket) →
    ("cold", "middle") → DEFAULT_OPENER if any bucket is empty.
    """
    rng = rng if rng is not None else random.Random()
    age_bucket = _age_to_bucket(age)

    for key in (
        (emotion, age_bucket),
        (emotion, "middle"),
        ("cold", age_bucket),
        ("cold", "middle"),
    ):
        pool = _OPENER_BANK.get(key)
        if pool:
            text = rng.choice(pool)
            delay = _sample_pickup_delay(emotion, rng)
            return OpenerChoice(text=text, emotion=emotion, age_bucket=age_bucket, pickup_delay_ms=delay)

    return OpenerChoice(
        text=DEFAULT_OPENER,
        emotion=emotion,
        age_bucket=age_bucket,
        pickup_delay_ms=_sample_pickup_delay(emotion, rng),
    )


__all__ = [
    "AgeBucket",
    "OpenerChoice",
    "DEFAULT_OPENER",
    "pick_opener",
    "_age_to_bucket",
    "_OPENER_BANK",
    "_PICKUP_DELAY_BY_MOOD",
]
