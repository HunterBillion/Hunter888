"""Lifelike barge-in reactions for /training call mode.

Phase F (2026-05-08).

When the user interrupts the AI mid-reply, the existing
`_handle_audio_interrupted` flow only truncates DB history and stashes
a state flag — there is NO immediate audio response. The next LLM call
embeds the «[ПЕРЕБИЛИ]» cue in its full reply, but the gap between
the interruption and any audible feedback is several seconds. Pilot
users perceive that as "AI didn't react".

This module provides a SHORT, ARCHETYPE-DRIVEN reaction phrase that
the WS handler synthesises and sends back IMMEDIATELY after receiving
`audio.interrupted`. The phrase fires before the next LLM-generated
reply, giving the conversation a "real human" feel.

Design — three orthogonal axes:
  1. ArchetypeGroup (10 groups, 100 archetypes covered) — "WHO is reacting"
  2. HumanFactor (anger | fatigue | anxiety | sarcasm — the 4 PO-confirmed
     emotions; pulled from session.active_factors highest intensity)
  3. played_chars bucket (low <30 / mid 30-100 / high >100 chars heard)
     — short interrupt = "А?" / surprise; long interrupt = "...я не закончил!"

Total: 10 × 4 × 3 = 120 cells. Each has 3-5 short Russian phrases.
Picker also respects:
  • current EmotionState (overrides to harsh phrases when state == hostile)
  • call stage (greeting → softer; objection → firmer)
  • silence rate (15% of interruptions get NO reaction — natural)

Selected phrase fits within 10-50 Russian characters so TTS round-trip
stays <500ms cold-cache and 0ms on second use (TTS cache key includes
voice + factor profile, so each archetype-factor combo has its own
slot, but the phrase pool is small enough to warm quickly).

The picker NEVER returns a long sentence — those belong in the LLM's
follow-up reply, not the barge reaction.
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from app.archetypes.profile import ArchetypeGroup
from app.archetypes.loader import _GROUP_MEMBERS

logger = logging.getLogger(__name__)


# Inverse map: archetype_code → ArchetypeGroup. Built lazily from
# _GROUP_MEMBERS so adding a new archetype to the loader auto-flows here.
_GROUP_BY_CODE: dict[str, ArchetypeGroup] = {}
for _grp, _codes in _GROUP_MEMBERS.items():
    for _c in _codes:
        _GROUP_BY_CODE[_c] = _grp


# Bucket boundaries for played_chars (how much of the AI's reply the
# user actually heard before interrupting).
PLAYED_LOW_MAX = 30   # less than 30 chars = barely started, surprise reaction
PLAYED_MID_MAX = 100  # 30-100 chars = mid-sentence, "не дайте сказать"
# > 100 chars = long-running reply got interrupted, full frustration


# 15% of interruptions get NO reaction at all — silence is sometimes
# the most natural response (especially for the AVOIDANCE group).
SILENCE_RATE = 0.15


# Reaction matrix — 10 groups × 4 factors × 3 played-chars buckets.
# Phrases are short Russian, 3-50 chars, no punctuation that confuses TTS.
# Curated to feel natural per archetype group.
_REACTIONS: dict[ArchetypeGroup, dict[str, dict[str, list[str]]]] = {
    # ─── RESISTANCE: skeptic, blamer, sarcastic, aggressive, hostile, ... ─
    ArchetypeGroup.RESISTANCE: {
        "anger": {
            "low":  ["Что?!", "Ну?", "Чего опять?", "Слушаю!"],
            "mid":  ["Дайте сказать!", "Я не договорил!", "Не перебивайте!"],
            "high": ["Опять перебиваете!", "Я ещё не закончил!", "Хватит уже!", "Слушайте до конца!"],
        },
        "anxiety": {
            "low":  ["А?", "Что вы?", "Простите?"],
            "mid":  ["Подождите...", "Я не закончил...", "Дайте мне сказать"],
            "high": ["Вы меня перебили...", "Я не успел договорить...", "Пожалуйста, дослушайте"],
        },
        "sarcasm": {
            "low":  ["Ага.", "Угу.", "Понятно..."],
            "mid":  ["Ну-ну.", "Конечно-конечно.", "Слушаю-слушаю."],
            "high": ["Ну да, конечно...", "Ясно всё с вами.", "Опять двадцать пять."],
        },
        "fatigue": {
            "low":  ["Что?", "А?", "Ну?"],
            "mid":  ["Слушайте...", "Подождите...", "Дайте сказать..."],
            "high": ["Я устал повторять...", "Опять то же самое...", "Сколько можно..."],
        },
    },
    # ─── EMOTIONAL: grateful, anxious, ashamed, overwhelmed, desperate, ... ─
    ArchetypeGroup.EMOTIONAL: {
        "anger": {
            "low":  ["А?!", "Что?!", "Чего?"],
            "mid":  ["Ну зачем?", "Дайте сказать!", "Я говорю!"],
            "high": ["Я говорил!", "Не перебивайте меня!", "Я хотел сказать..."],
        },
        "anxiety": {
            "low":  ["Ой...", "А?", "Простите..."],
            "mid":  ["Подождите, я не...", "Я хотел сказать...", "Можно я договорю?"],
            "high": ["Я просто хотел...", "Я не успел...", "Простите, можно я закончу?"],
        },
        "sarcasm": {
            "low":  ["Хм.", "Ага.", "Слушаю."],
            "mid":  ["Понятно...", "Конечно...", "Как скажете."],
            "high": ["Ну, видимо, не моя очередь.", "Понятно, я молчу.", "Хорошо, говорите вы."],
        },
        "fatigue": {
            "low":  ["А?", "Что?", "Простите?"],
            "mid":  ["Ох...", "Я устал...", "Подождите..."],
            "high": ["У меня сил нет всё повторять...", "Я устал, дайте договорить...", "Не могу так быстро..."],
        },
    },
    # ─── CONTROL: pragmatic, shopper, negotiator, know_it_all, manipulator, ... ─
    ArchetypeGroup.CONTROL: {
        "anger": {
            "low":  ["Так.", "Что?", "Да?"],
            "mid":  ["Я ещё говорил.", "Дослушайте.", "Один момент."],
            "high": ["Я не закончил мысль.", "Дайте мне договорить.", "Перебивать невежливо."],
        },
        "anxiety": {
            "low":  ["А?", "Что вы?", "Так?"],
            "mid":  ["Минутку...", "Я не успел...", "Подождите секунду."],
            "high": ["Вы меня сбили...", "Я потерял мысль...", "Можно я завершу?"],
        },
        "sarcasm": {
            "low":  ["Ну-ну.", "Слушаю.", "Так-так."],
            "mid":  ["Ясно.", "Принято.", "Замечательно."],
            "high": ["Видимо, моё мнение неважно.", "Ладно, рассказывайте вы.", "Я молчу, говорите."],
        },
        "fatigue": {
            "low":  ["Да?", "Слушаю.", "Что?"],
            "mid":  ["Один момент...", "Подождите...", "Дайте подумать."],
            "high": ["Слишком быстро говорите.", "Я не успеваю за вами.", "Помедленнее давайте."],
        },
    },
    # ─── AVOIDANCE: passive, delegator, avoidant, paranoid, procrastinator, ... ─
    # Avoidance group is QUIETER — many cells go to "" (silence) randomly.
    ArchetypeGroup.AVOIDANCE: {
        "anger": {
            "low":  ["А?", "Что?", "Ну?"],
            "mid":  ["Хорошо, говорите.", "Ладно.", "Понял."],
            "high": ["Ну ладно...", "Хорошо.", "Как скажете."],
        },
        "anxiety": {
            "low":  ["А?", "Простите?", "Что вы?"],
            "mid":  ["Ой...", "Простите...", "Я не..."],
            "high": ["Простите, я вас отвлёк...", "Извините...", "Я лучше потом..."],
        },
        "sarcasm": {
            "low":  ["Угу.", "Ага.", "Так."],
            "mid":  ["Понял.", "Ясно.", "Принято."],
            "high": ["Ну хорошо.", "Раз вы так считаете.", "Воля ваша."],
        },
        "fatigue": {
            "low":  ["А?", "Что?", "Слушаю."],
            "mid":  ["Хорошо...", "Угу...", "Ладно..."],
            "high": ["Я уже устал...", "Может быть позже?", "Хорошо, как скажете."],
        },
    },
    # ─── SPECIAL: referred, returner, rushed, couple, elderly, ... ─
    ArchetypeGroup.SPECIAL: {
        "anger": {
            "low":  ["Что?", "А?", "Ну?"],
            "mid":  ["Я говорю!", "Дайте сказать!", "Минутку!"],
            "high": ["Сколько можно перебивать!", "Я не закончил!", "Слушайте, наконец!"],
        },
        "anxiety": {
            "low":  ["А?", "Простите?", "Что?"],
            "mid":  ["Я не успел...", "Подождите...", "Можно?"],
            "high": ["Я не успел сказать...", "Простите, я хотел...", "Можно я закончу?"],
        },
        "sarcasm": {
            "low":  ["Хм.", "Угу.", "Так."],
            "mid":  ["Ясно.", "Понятно.", "Замечательно."],
            "high": ["Ну, рассказывайте.", "Я просто слушаю.", "Видимо, говорю не я."],
        },
        "fatigue": {
            "low":  ["Что?", "Да?", "А?"],
            "mid":  ["Ох, погодите...", "Не торопитесь...", "Минуточку..."],
            "high": ["Я не успеваю...", "Помедленнее, пожалуйста.", "У меня голова кругом..."],
        },
    },
    # ─── COGNITIVE: overthinker, concrete, storyteller, misinformed, ... ─
    ArchetypeGroup.COGNITIVE: {
        "anger": {
            "low":  ["Что?", "А?", "Ну?"],
            "mid":  ["Я мысль не закончил.", "Дайте подумать.", "Минутку."],
            "high": ["Вы меня сбили с мысли.", "Я не закончил рассуждение.", "Дайте мне подумать."],
        },
        "anxiety": {
            "low":  ["А?", "Что?", "Простите?"],
            "mid":  ["Подождите, я думаю...", "Минуту...", "Я не уверен..."],
            "high": ["Вы меня запутали...", "Я потерял нить...", "Можно ещё раз?"],
        },
        "sarcasm": {
            "low":  ["Хм.", "Ага.", "Угу."],
            "mid":  ["Понятно.", "Любопытно.", "Интересно."],
            "high": ["Логично.", "Безупречная логика.", "Очень содержательно."],
        },
        "fatigue": {
            "low":  ["Что?", "А?", "Да?"],
            "mid":  ["Сложно...", "Не понимаю...", "Подождите..."],
            "high": ["Я уже путаюсь...", "Слишком много информации...", "Помедленнее, не успеваю..."],
        },
    },
    # ─── SOCIAL: family_man, influenced, reputation_guard, ... ─
    ArchetypeGroup.SOCIAL: {
        "anger": {
            "low":  ["Что?", "Ну?", "А?"],
            "mid":  ["Я говорю!", "Дайте сказать!", "Не перебивайте!"],
            "high": ["Я ещё не закончил!", "Это невежливо!", "Послушайте до конца!"],
        },
        "anxiety": {
            "low":  ["Ой...", "А?", "Простите?"],
            "mid":  ["Подождите...", "Я не успел...", "Можно?"],
            "high": ["Я хотел сказать...", "Простите, можно я закончу?", "Я не успел договорить..."],
        },
        "sarcasm": {
            "low":  ["Ага.", "Угу.", "Так."],
            "mid":  ["Понятно.", "Замечательно.", "Прекрасно."],
            "high": ["Видимо, моё мнение неважно.", "Понятно всё с вами.", "Ну, говорите."],
        },
        "fatigue": {
            "low":  ["Что?", "А?", "Да?"],
            "mid":  ["Ох...", "Подождите...", "Я устал..."],
            "high": ["У меня нет сил спорить...", "Помедленнее, прошу...", "Я устал от этого..."],
        },
    },
    # ─── TEMPORAL: just_fired, court_notice, salary_arrest, ... ─
    # Temporal archetypes are high-stakes — reactions skew firmer/more direct.
    ArchetypeGroup.TEMPORAL: {
        "anger": {
            "low":  ["Что?!", "Ну?!", "Чего?!"],
            "mid":  ["Я говорю!", "Дайте сказать!", "Послушайте!"],
            "high": ["Хватит перебивать!", "Я не закончил!", "Дайте мне договорить!"],
        },
        "anxiety": {
            "low":  ["А?", "Что?", "Простите?"],
            "mid":  ["Подождите...", "Я не закончил...", "Можно?"],
            "high": ["Я не успел сказать главное...", "Это очень важно...", "Простите, дослушайте..."],
        },
        "sarcasm": {
            "low":  ["Ну.", "Угу.", "Ага."],
            "mid":  ["Понятно.", "Ясно.", "Принято."],
            "high": ["Видимо, моя ситуация вам безразлична.", "Понятно, у вас регламент.", "Ну, говорите."],
        },
        "fatigue": {
            "low":  ["А?", "Что?", "Да?"],
            "mid":  ["Я устал объяснять...", "Подождите...", "Дайте сказать..."],
            "high": ["Я уже не могу всё это повторять...", "Сколько можно...", "Я устал от этого всего..."],
        },
    },
    # ─── PROFESSIONAL: teacher, doctor, military, accountant, ... ─
    # Professional archetypes are precise — short, direct reactions.
    ArchetypeGroup.PROFESSIONAL: {
        "anger": {
            "low":  ["Что?", "Да?", "Ну?"],
            "mid":  ["Я не закончил.", "Дослушайте.", "Минутку."],
            "high": ["Я не закончил мысль.", "Дайте договорить.", "Перебивать невежливо."],
        },
        "anxiety": {
            "low":  ["А?", "Что?", "Слушаю."],
            "mid":  ["Подождите...", "Минуту...", "Я не успел."],
            "high": ["Я не успел изложить...", "Можно я завершу мысль?", "Простите, мне важно договорить."],
        },
        "sarcasm": {
            "low":  ["Хм.", "Угу.", "Так."],
            "mid":  ["Понятно.", "Принято.", "Зафиксировал."],
            "high": ["Видимо, диалог окончен.", "Понятно, монолог не предусмотрен.", "Хорошо, ваш ход."],
        },
        "fatigue": {
            "low":  ["Что?", "Да?", "Слушаю."],
            "mid":  ["Минуту...", "Подождите...", "Один момент."],
            "high": ["Слишком быстрый темп.", "Помедленнее, прошу.", "Я не успеваю."],
        },
    },
    # ─── COMPOUND: aggressive_desperate, manipulator_crying, ... ─
    # Compound archetypes mix two — reactions are sharper, more theatrical.
    ArchetypeGroup.COMPOUND: {
        "anger": {
            "low":  ["Что?!", "Ну?!", "Что вы?!"],
            "mid":  ["Дайте сказать!", "Я не закончил!", "Слушайте!"],
            "high": ["Опять перебиваете!", "Я ещё не сказал главного!", "Хватит уже!"],
        },
        "anxiety": {
            "low":  ["Ой!", "А?", "Простите?"],
            "mid":  ["Я не успел...", "Подождите...", "Можно?"],
            "high": ["Вы меня перебили...", "Я хотел сказать важное...", "Простите, дослушайте..."],
        },
        "sarcasm": {
            "low":  ["Ну.", "Угу.", "Ага."],
            "mid":  ["Понятно.", "Конечно.", "Замечательно."],
            "high": ["Ну да, моё мнение никому не нужно.", "Понятно всё с вами.", "Хорошо, я молчу."],
        },
        "fatigue": {
            "low":  ["А?", "Что?", "Да?"],
            "mid":  ["Я устал...", "Подождите...", "Ох..."],
            "high": ["У меня уже голова разболелась...", "Я устал от этого...", "Помедленнее, пожалуйста..."],
        },
    },
}


def _bucket_played_chars(played_chars: int) -> str:
    """Return 'low' | 'mid' | 'high' bucket for played_chars value."""
    if played_chars <= PLAYED_LOW_MAX:
        return "low"
    if played_chars <= PLAYED_MID_MAX:
        return "mid"
    return "high"


def _resolve_group(archetype_code: Optional[str]) -> ArchetypeGroup:
    """Map archetype code to its group with safe fallback to RESISTANCE."""
    if not archetype_code:
        return ArchetypeGroup.RESISTANCE
    return _GROUP_BY_CODE.get(archetype_code, ArchetypeGroup.RESISTANCE)


def _primary_factor(active_factors: list[dict] | None) -> str:
    """Pick the highest-intensity active factor or 'anxiety' as default.

    `active_factors` shape: [{"factor": "anger", "intensity": 0.7, ...}, ...]
    """
    if not active_factors:
        return "anxiety"
    try:
        ranked = sorted(
            active_factors,
            key=lambda f: float(f.get("intensity") or 0.0),
            reverse=True,
        )
        top = ranked[0].get("factor") or "anxiety"
        if top in ("anger", "fatigue", "anxiety", "sarcasm"):
            return top
        return "anxiety"
    except Exception:
        return "anxiety"


def pick_barge_reaction(
    archetype_code: Optional[str],
    active_factors: list[dict] | None,
    played_chars: int,
    current_emotion: Optional[str] = None,
    current_stage: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> Optional[str]:
    """Pick a short reaction phrase for an interruption.

    Returns None when reaction should be silent (15% rate, or when
    the conversation context makes a reaction inappropriate — e.g.
    very early greeting stage where a short 'Что?' fits, but we want
    occasional silence too).

    Priority overrides:
      • emotion='hostile' or 'hangup' → always force 'anger' factor
        (overrides whatever active_factors says — a hostile client
        ignores their own anxiety profile and snaps).
      • stage='greeting' AND played_chars==0 → softer pool always
        (interrupting "Алло?" deserves "А?" not "хватит уже!").
    """
    rng = rng or random
    if rng.random() < SILENCE_RATE:
        return None

    group = _resolve_group(archetype_code)
    factor = _primary_factor(active_factors)

    # Hostile/hangup emotion overrides factor → forced anger
    if current_emotion in ("hostile", "hangup"):
        factor = "anger"

    bucket = _bucket_played_chars(played_chars)

    # Greeting + zero played → force soft 'anxiety' bucket regardless
    if current_stage == "greeting" and played_chars == 0:
        factor = "anxiety"
        bucket = "low"

    pool = _REACTIONS.get(group, {}).get(factor, {}).get(bucket)
    if not pool:
        # Fallback chain: same group, anxiety, low
        pool = _REACTIONS.get(group, {}).get("anxiety", {}).get("low")
    if not pool:
        # Hard fallback — universal short reaction
        return "А?"

    chosen = rng.choice(pool)
    logger.debug(
        "barge_reaction picked: archetype=%s group=%s factor=%s bucket=%s emotion=%s stage=%s -> %r",
        archetype_code, group.value, factor, bucket, current_emotion, current_stage, chosen,
    )
    return chosen
