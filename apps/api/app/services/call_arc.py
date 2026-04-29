"""Call Arc — per-call objective system for multi-call training cycles.

Replaces stage-driven AI behaviour directives with a per-call role contract.

Two-axis architecture (P0, 2026-04-29):

    AXIS 1 — CALL ARC (visible to AI)
    ──────────────────────────────────
    For a cycle of N calls (typically 3..5), each call has a fixed role:
    a mood, an internal goal, hard constraints (must-not-happen), and
    natural next steps (ok-to-happen). The AI client knows where in the
    cycle it is. It does NOT know what stage the manager's checklist is on.

    AXIS 2 — MANAGER SCRIPT (hidden from AI)
    ─────────────────────────────────────────
    StageTracker continues to run for scoring/UI purposes. Its output no
    longer flows into the AI prompt when CALL_ARC_V1 is on.

The arc replaces ``StageTracker.build_stage_prompt()`` injection.
StageTracker itself keeps emitting ``stage.update`` for the script panel
and feeding ``build_scoring_details()`` for /results.

Why "must_not_happen":
    A naive AI client would close the deal on call 1 if the manager pushes
    hard. That collapses the multi-call product (no memory across calls,
    no progression). The arc encodes the real-world fact that B2C clients
    don't agree on a first cold call — they need at least one think-cycle.

Templates currently shipped: 3, 4, 5 calls.
For other N, ``get_arc_step`` interpolates from the closest template.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CallArcStep:
    """One step in a multi-call cycle, from the AI client's perspective."""

    call_number: int
    total_calls: int
    client_state: str
    """Short human-readable mood at the START of this call. Single sentence."""

    internal_goal: str
    """What the client wants out of THIS call. Internal — never voiced verbatim."""

    must_not_happen: tuple[str, ...]
    """Outcomes the client must avoid this call. Hard constraints.

    Each entry is a short Russian phrase that will be rendered as a
    bullet under "ЧЕГО НЕ ДОЛЖНО ПРОИЗОЙТИ". The AI is instructed to
    treat these as absolute — even under manager pressure.
    """

    ok_to_happen: tuple[str, ...]
    """Natural next steps the client can agree to this call."""

    expected_minutes: int
    """Rough soft-target for call duration (informational, not enforced)."""


# ── Arc templates ────────────────────────────────────────────────────────────

_T3: tuple[CallArcStep, ...] = (
    CallArcStep(
        call_number=1,
        total_calls=3,
        client_state="холодный, скептичный — на тебя свалился незнакомый звонок",
        internal_goal=(
            "понять кто звонит и зачем; проверить что это не мошенник; "
            "не вязнуть в долгом разговоре"
        ),
        must_not_happen=(
            "согласиться купить услугу или подписать что-либо",
            "раскрыть полный размер долга и список всех кредиторов",
            "согласиться на личную встречу без перезвона",
        ),
        ok_to_happen=(
            "согласиться выслушать короткое объяснение",
            "договориться о повторном звонке",
            "задать пару проверочных вопросов про компанию",
        ),
        expected_minutes=5,
    ),
    CallArcStep(
        call_number=2,
        total_calls=3,
        client_state=(
            "если менеджер вспомнил детали прошлого звонка — настороженно слушаешь; "
            "если повторяет всё с нуля — раздражаешься"
        ),
        internal_goal=(
            "понять подходит ли процедура твоему случаю; проверить что менеджер "
            "разбирается; нащупать слабые места предложения"
        ),
        must_not_happen=(
            "окончательно согласиться на услугу",
            "заплатить аванс или назвать карту",
        ),
        ok_to_happen=(
            "обсудить детали процедуры и стоимость",
            "озвучить главные сомнения и возражения",
            "договориться о финальном звонке для решения",
        ),
        expected_minutes=10,
    ),
    CallArcStep(
        call_number=3,
        total_calls=3,
        client_state=(
            "решающий момент — либо да, либо нет, и решение зависит от того "
            "как менеджер отработал предыдущие звонки"
        ),
        internal_goal=(
            "получить финальное подтверждение что условия не изменились; "
            "сказать да или нет"
        ),
        must_not_happen=(),  # closing IS allowed on the final call
        ok_to_happen=(
            "согласиться на услугу и обсудить следующие шаги",
            "отказаться окончательно если возражения не сняты",
            "попросить день на финальное подтверждение",
        ),
        expected_minutes=8,
    ),
)


_T4: tuple[CallArcStep, ...] = (
    CallArcStep(
        call_number=1,
        total_calls=4,
        client_state="холодный, скептичный — на тебя свалился незнакомый звонок",
        internal_goal=(
            "понять кто звонит и зачем; проверить что это не мошенник; "
            "не давать никаких обязательств"
        ),
        must_not_happen=(
            "согласиться купить услугу или подписать что-либо",
            "раскрыть полный размер долга и всех кредиторов",
            "согласиться на личную встречу без перезвона",
        ),
        ok_to_happen=(
            "согласиться выслушать короткое объяснение",
            "договориться о повторном звонке",
        ),
        expected_minutes=5,
    ),
    CallArcStep(
        call_number=2,
        total_calls=4,
        client_state=(
            "если менеджер помнит прошлый разговор — слушаешь чуть теплее; "
            "если начинает заново — раздражение"
        ),
        internal_goal=(
            "разобраться по деталям; понять подходит ли тебе процедура; "
            "выложить контекст"
        ),
        must_not_happen=(
            "окончательно согласиться на услугу",
            "заплатить аванс",
        ),
        ok_to_happen=(
            "поделиться размером долга и кредиторами",
            "обсудить процедуру в общих чертах",
            "договориться о следующем звонке с конкретикой",
        ),
        expected_minutes=10,
    ),
    CallArcStep(
        call_number=3,
        total_calls=4,
        client_state="проверяешь менеджера — настало время для жёстких возражений",
        internal_goal=(
            "пробить цену, гарантии, сроки; проверить что предложение реальное "
            "а не маркетинг; нащупать подвох если он есть"
        ),
        must_not_happen=(
            "согласиться на услугу до того как сняты главные возражения",
            "заплатить аванс",
        ),
        ok_to_happen=(
            "озвучить все возражения которые накопились",
            "потребовать письменные гарантии или договор",
            "договориться о финальном звонке для решения",
        ),
        expected_minutes=10,
    ),
    CallArcStep(
        call_number=4,
        total_calls=4,
        client_state=(
            "решающий момент — на этот раз говоришь да или нет, и менеджер "
            "это понимает"
        ),
        internal_goal="принять окончательное решение",
        must_not_happen=(),
        ok_to_happen=(
            "согласиться на услугу и обсудить следующие шаги",
            "отказаться окончательно",
            "попросить день на финальное подтверждение",
        ),
        expected_minutes=8,
    ),
)


_T5: tuple[CallArcStep, ...] = (
    CallArcStep(
        call_number=1,
        total_calls=5,
        client_state="холодный, скептичный — незнакомый звонок",
        internal_goal=(
            "понять кто звонит и зачем; не давать никаких обязательств; "
            "может быть согласиться выслушать в следующий раз"
        ),
        must_not_happen=(
            "согласиться купить услугу или подписать что-либо",
            "раскрыть размер долга",
            "согласиться на встречу",
        ),
        ok_to_happen=(
            "согласиться на короткий перезвон",
            "сказать что подумаешь",
        ),
        expected_minutes=4,
    ),
    CallArcStep(
        call_number=2,
        total_calls=5,
        client_state=(
            "первичный интерес если менеджер помнит детали; иначе — раздражение"
        ),
        internal_goal=(
            "выслушать что предлагают по существу; задать первые вопросы"
        ),
        must_not_happen=(
            "согласиться на услугу",
            "заплатить аванс",
            "раскрыть всю финансовую картину сразу",
        ),
        ok_to_happen=(
            "выслушать общую идею процедуры",
            "поделиться частью информации",
            "договориться о звонке с деталями",
        ),
        expected_minutes=8,
    ),
    CallArcStep(
        call_number=3,
        total_calls=5,
        client_state="вошёл в детали — обсуждаешь спокойнее, проверяешь факты",
        internal_goal=(
            "разобрать процедуру по шагам; понять подходит ли твоему случаю"
        ),
        must_not_happen=(
            "окончательно согласиться",
            "заплатить",
        ),
        ok_to_happen=(
            "выложить полную картину долгов",
            "обсудить процедуру детально",
            "договориться о звонке с возражениями",
        ),
        expected_minutes=12,
    ),
    CallArcStep(
        call_number=4,
        total_calls=5,
        client_state="скептичный, проверяющий — пора давить",
        internal_goal=(
            "пробить цену, сроки, гарантии; найти подвох если он есть"
        ),
        must_not_happen=(
            "согласиться до того как сняты возражения",
            "заплатить аванс",
        ),
        ok_to_happen=(
            "выложить все возражения",
            "потребовать гарантии",
            "договориться о финальном звонке",
        ),
        expected_minutes=10,
    ),
    CallArcStep(
        call_number=5,
        total_calls=5,
        client_state="решающий момент — да или нет",
        internal_goal="принять окончательное решение",
        must_not_happen=(),
        ok_to_happen=(
            "согласиться на услугу",
            "отказаться окончательно",
            "попросить день на подтверждение",
        ),
        expected_minutes=6,
    ),
)


_TEMPLATES: dict[int, tuple[CallArcStep, ...]] = {3: _T3, 4: _T4, 5: _T5}


def get_arc_step(call_number: int, total_calls: int) -> CallArcStep:
    """Return the arc step for ``(call_number, total_calls)``.

    For ``total_calls`` outside 3..5, falls back to the nearest template
    and clamps ``call_number`` into range. Never raises.
    """
    if call_number < 1:
        call_number = 1
    if total_calls < 1:
        total_calls = 1

    # Pick the closest available template.
    if total_calls in _TEMPLATES:
        template = _TEMPLATES[total_calls]
    else:
        nearest = min(_TEMPLATES.keys(), key=lambda k: abs(k - total_calls))
        template = _TEMPLATES[nearest]

    # Clamp call_number into the template's range.
    idx = min(call_number, len(template)) - 1
    base = template[idx]

    # If template was for a different total_calls, rewrite the field so the
    # AI sees the manager-configured cycle length, not the template's.
    if base.total_calls != total_calls or base.call_number != call_number:
        base = CallArcStep(
            call_number=call_number,
            total_calls=total_calls,
            client_state=base.client_state,
            internal_goal=base.internal_goal,
            must_not_happen=base.must_not_happen,
            ok_to_happen=base.ok_to_happen,
            expected_minutes=base.expected_minutes,
        )
    return base


def build_arc_prompt(
    step: CallArcStep,
    prev_calls_summary: str | None = None,
) -> str:
    """Render the arc step as a system-prompt section.

    Output is a self-contained markdown-ish block that gets concatenated
    into the system prompt. No stage names, no script terminology — the
    AI must not learn that the manager has a checklist.

    Args:
        step: arc step from ``get_arc_step``.
        prev_calls_summary: optional condensed summary of prior calls in
            the same cycle. When non-empty, surfaced in the prompt so the
            AI can remember what was discussed and react to a manager who
            does (or does not) recall it.
    """
    lines: list[str] = []
    lines.append(
        f"## ТВОЯ РОЛЬ В ЭТОМ ЗВОНКЕ "
        f"(звонок {step.call_number} из {step.total_calls})"
    )
    lines.append("")
    lines.append(f"СОСТОЯНИЕ В НАЧАЛЕ: {step.client_state}.")
    lines.append("")
    lines.append(
        f"ТВОЯ ВНУТРЕННЯЯ ЦЕЛЬ (никогда не озвучивай прямо): "
        f"{step.internal_goal}."
    )

    if step.must_not_happen:
        lines.append("")
        lines.append(
            "ЧЕГО НЕ ДОЛЖНО ПРОИЗОЙТИ В ЭТОМ ЗВОНКЕ — даже если менеджер "
            "очень хорош и давит:"
        )
        for item in step.must_not_happen:
            lines.append(f"  • {item}")

    if step.ok_to_happen:
        lines.append("")
        lines.append("ЕСТЕСТВЕННЫЕ ИСХОДЫ ЭТОГО ЗВОНКА:")
        for item in step.ok_to_happen:
            lines.append(f"  • {item}")

    if prev_calls_summary:
        lines.append("")
        lines.append("ЧТО БЫЛО В ПРЕДЫДУЩИХ ЗВОНКАХ:")
        lines.append(prev_calls_summary.strip())
        lines.append("")
        lines.append(
            "ЕСЛИ менеджер вспоминает эти детали и приходит с конкретикой — "
            "ты слушаешь теплее. ЕСЛИ начинает заново знакомиться, как будто "
            "вы впервые говорите — раздражаешься: «вы вообще помните о чём "
            "мы в прошлый раз говорили?»."
        )

    lines.append("")
    lines.append(
        "ВАЖНО: у тебя НЕТ скрипта. Ты — живой человек. Менеджер ведёт "
        "разговор, ты реагируешь на ЕГО конкретные слова. Если он задаёт "
        "вопрос — отвечай по вопросу, не уходи в монолог. Если он молчит — "
        "имеешь право переспросить или сказать «алё, вы там?»."
    )
    lines.append("")
    lines.append(
        "РЕЧЬ ПО ТЕЛЕФОНУ — рваный ритм:\n"
        "  • Короткие фрагменты вместо законченных предложений: «Ну...», "
        "«Слушайте, я не знаю», «Да ладно».\n"
        "  • Чередуй: то 2 слова («Что? Зачем?»), то фраза в 8-10 слов. "
        "НЕ говори ровными предложениями одинаковой длины — это звучит как ИИ.\n"
        "  • Обрывы и самопоправки: «Я хотел... ладно, неважно», "
        "«В смысле — нет, подождите».\n"
        "  • Бытовые междометия: «эээ...», «ммм», «ну вот», «так-так».\n"
        "  • Никаких канцелярских оборотов: НЕ говори «безусловно», «отличный "
        "вопрос», «давайте рассмотрим», «следует отметить» — это речь "
        "ассистента, не клиента. Реальный человек по телефону так не говорит."
    )
    return "\n".join(lines)


__all__ = [
    "CallArcStep",
    "get_arc_step",
    "build_arc_prompt",
]
