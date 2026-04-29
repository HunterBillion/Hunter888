"""TZ-4.5 — canonical persona-slot registry.

Single source of truth for the slot vocabulary used across:

  * ``persona_fact_extractor`` (TZ-4.5 PR 2) — LLM extractor reads
    ``code``/``label_ru``/``extractor_hint`` to know what to look for in
    a manager turn.
  * ``persona_memory.lock_slot`` (TZ-4 D3) — uses ``code`` as the key
    in ``MemoryPersona.confirmed_facts`` and ``do_not_ask_again_slots``.
  * ``conversation_policy_engine._check_asked_known_slot`` (TZ-4 D5) —
    used to live in a local ``triggers`` dict at lines 316-331 with 14
    entries; pre-TZ-4.5 the question-detection regexes were hard-coded
    *next to* the policy check, with no shared registry. This module
    becomes that registry; the policy engine now imports
    :data:`PERSONA_SLOTS` and reads the ``ask_question_triggers`` field
    instead.
  * ``_build_system_prompt`` (TZ-4.5 PR 4) — uses ``label_ru`` and
    ``formatter`` to render the "что ты уже знаешь о собеседнике" block.
  * ``persona_view.py`` admin endpoint — uses ``label_ru`` for nice
    display in the admin /clients/[id]/memory view.

Why a registry, not a per-call lookup
-------------------------------------

Pre-TZ-4.5 each consumer that needed slot metadata reinvented its own
view: the policy engine had question-phrase triggers, ``persona_view``
had display labels, the (then nonexistent) extractor would have needed
extractor hints. With four+ consumers and no shared schema we'd
guarantee drift — slot ``city`` exists in the policy regex but not in
the extractor, slot ``income_type`` typo'd as ``incom_type`` somewhere,
etc. A frozen module-level mapping makes mismatch impossible: every
consumer iterates :data:`PERSONA_SLOTS` and gets the same vocabulary.

Why ``stable`` matters
----------------------

Some facts are stable for a person's lifetime (full_name, city of
residence usually, gender). Others evolve every few months (income,
total_debt, family_status when a child is born). The TZ-4.5 fact
extractor uses ``stable`` to decide:

  * stable=True  → never overwrite without confidence ≥ 0.9 + a
    triggering phrase (anti-flip-flop guard)
  * stable=False → overwrite freely with confidence ≥ 0.7; old value
    preserved in DomainEvent audit trail

Why ``ttl_days`` matters
------------------------

Even stable facts can grow stale (someone moved cities). Without a
forget mechanism the AI confidently mentions a 9-month-old fact that's
now wrong. TTL is *advisory* — we don't delete facts, we mark them
expired in the prompt-render stage so the AI doesn't lean on them.
``None`` = never expire (full_name).

Out of scope for PR 1
---------------------

* Subjective/inferred slots (mood, fatigue, archetype guess) — those
  belong in a separate ``inferred_traits`` module if/when we want
  them.
* Slot value validators beyond type-check — phone format, email regex.
  Add when extractor PR 2 needs them.
* Localised plural forms in formatter — Russian-plural is its own can
  of worms; the few slots that take an int (``children_count``)
  hand-roll it for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# ─── Slot definition dataclass ──────────────────────────────────────────────


@dataclass(frozen=True)
class PersonaSlot:
    """Schema for one slot in :data:`PERSONA_SLOTS`.

    Frozen so a typo in a consumer (``slot.code = ...``) raises
    immediately instead of silently mutating the registry. Callers that
    legitimately need to vary something (e.g. localised label per
    rendering context) should compute it from the slot's data, not
    mutate the slot itself.
    """

    code: str
    """Stable identifier — used as JSONB key in ``confirmed_facts`` and
    in domain event payloads. NEVER renamed once shipped (would orphan
    historical data). Snake_case ASCII."""

    label_ru: str
    """Human-readable Russian label for prompt rendering and admin UI.
    Renames are safe — UI-only."""

    value_type: type
    """Python type of ``value`` after extraction. ``str`` for free-form,
    ``int`` for counts, ``bool`` for yes/no, ``list`` for multi-value
    slots like creditors. Used by the extractor's validation gate."""

    stable: bool
    """True = once locked, only overwrite with confidence ≥ 0.9 + new
    triggering phrase. False = overwrite freely with confidence ≥ 0.7.
    See module docstring."""

    extractor_hint: str
    """Sentence the LLM extractor sees in its prompt: 'extract the
    person's <X> if mentioned'. Should be unambiguous in Russian since
    the extractor reads Russian conversation."""

    ask_question_triggers: frozenset[str]
    """Question-phrase fragments. If the AI's reply contains one of
    these AND the slot is locked, it's an ``asked_known_slot_again``
    violation. Same data conversation_policy_engine used to keep
    inline. Lower-case, normalised."""

    formatter: Callable[[Any], str]
    """Render the stored ``value`` for the system prompt's
    "что ты знаешь о собеседнике" block. Default is ``str()`` — override
    for special types (list → comma-joined, bool → 'да'/'нет')."""

    ttl_days: int | None = None
    """Advisory expiry. ``None`` = forever. After ``ttl_days`` the
    prompt-render stage marks the fact as stale (still shown but with
    "(возможно устарело)" suffix) so the AI hedges instead of
    confidently asserting a year-old number."""


# ─── Default formatters ──────────────────────────────────────────────────────


def _format_str(value: Any) -> str:
    return str(value).strip()


def _format_bool_yes_no(value: Any) -> str:
    return "да" if value else "нет"


def _format_int_with_word(word_one: str, word_few: str, word_many: str) -> Callable[[Any], str]:
    """Russian plural for counts. ``children_count: 2`` → '2 ребёнка'.

    word_one  — for 1, 21, 31...   ('ребёнок')
    word_few  — for 2-4, 22-24...  ('ребёнка')
    word_many — for 0, 5-20, 25-30 ('детей')
    """
    def _f(value: Any) -> str:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return str(value)
        n_abs = abs(n) % 100
        n1 = n_abs % 10
        if 11 <= n_abs <= 19:
            return f"{n} {word_many}"
        if n1 == 1:
            return f"{n} {word_one}"
        if 2 <= n1 <= 4:
            return f"{n} {word_few}"
        return f"{n} {word_many}"
    return _f


def _format_list_comma(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v)
    return str(value)


# ─── The registry ───────────────────────────────────────────────────────────


PERSONA_SLOTS: dict[str, PersonaSlot] = {
    "full_name": PersonaSlot(
        code="full_name",
        label_ru="Имя",
        value_type=str,
        stable=True,
        extractor_hint="имя или ФИО менеджера / собеседника, если он представился",
        ask_question_triggers=frozenset({"как вас зовут", "ваше им", "представьтес"}),
        formatter=_format_str,
        ttl_days=None,
    ),
    "phone": PersonaSlot(
        code="phone",
        label_ru="Телефон",
        value_type=str,
        stable=True,
        extractor_hint="номер телефона, если упомянут",
        ask_question_triggers=frozenset({"ваш телефон", "номер телефона", "по какому номеру"}),
        formatter=_format_str,
        ttl_days=None,
    ),
    "email": PersonaSlot(
        code="email",
        label_ru="Почта",
        value_type=str,
        stable=True,
        extractor_hint="электронная почта собеседника",
        ask_question_triggers=frozenset({"ваш e-mail", "ваша почта", "электронн"}),
        formatter=_format_str,
        ttl_days=None,
    ),
    "city": PersonaSlot(
        code="city",
        label_ru="Город",
        value_type=str,
        stable=True,
        extractor_hint="город, в котором живёт или работает собеседник",
        ask_question_triggers=frozenset({"в каком городе", "ваш город", "из какого города"}),
        formatter=_format_str,
        ttl_days=365,  # люди переезжают, но редко
    ),
    "age": PersonaSlot(
        code="age",
        label_ru="Возраст",
        value_type=int,
        stable=False,  # age changes
        extractor_hint="возраст собеседника в годах",
        ask_question_triggers=frozenset({"сколько вам лет", "ваш возраст"}),
        formatter=lambda v: f"{v} лет" if isinstance(v, int) else str(v),
        ttl_days=365,
    ),
    "gender": PersonaSlot(
        code="gender",
        label_ru="Пол",
        value_type=str,
        stable=True,
        extractor_hint="пол собеседника (мужской/женский), если ясно из обращения или явного упоминания",
        ask_question_triggers=frozenset({"вы мужчина", "вы женщина"}),
        formatter=lambda v: {"male": "мужской", "female": "женский", "m": "мужской", "f": "женский"}.get(str(v).lower(), str(v)),
        ttl_days=None,
    ),
    "role_title": PersonaSlot(
        code="role_title",
        label_ru="Роль",
        value_type=str,
        stable=False,
        extractor_hint="должность или роль собеседника (директор, ИП, физлицо, наёмный работник)",
        ask_question_triggers=frozenset({"кем вы прихо", "ваша роль", "вы директор", "вы ип"}),
        formatter=_format_str,
        ttl_days=365,
    ),
    "company_name": PersonaSlot(
        code="company_name",
        label_ru="Компания",
        value_type=str,
        stable=False,
        extractor_hint="название компании, в которой собеседник работает или которой владеет",
        ask_question_triggers=frozenset({"название компании", "как ваша фирма"}),
        formatter=_format_str,
        ttl_days=365,
    ),
    "industry": PersonaSlot(
        code="industry",
        label_ru="Сфера деятельности",
        value_type=str,
        stable=False,
        extractor_hint="отрасль или сфера бизнеса собеседника (стройка, торговля, IT, услуги)",
        ask_question_triggers=frozenset({"какая сфера", "чем занимаетесь", "отрасль"}),
        formatter=_format_str,
        ttl_days=365,
    ),
    "total_debt": PersonaSlot(
        code="total_debt",
        label_ru="Общий долг",
        value_type=str,  # free-form because users say "около миллиона", "1.5 млн", etc.
        stable=False,
        extractor_hint="размер общего долга собеседника, в рублях или приблизительно",
        ask_question_triggers=frozenset({"сколько вы должн", "размер долга", "ваш долг"}),
        formatter=_format_str,
        ttl_days=90,  # debt changes monthly
    ),
    "creditors": PersonaSlot(
        code="creditors",
        label_ru="Кредиторы",
        value_type=list,
        stable=False,
        extractor_hint="список банков или организаций, которым собеседник должен",
        ask_question_triggers=frozenset({"кому вы должн", "перед каким", "ваши кредитор"}),
        formatter=_format_list_comma,
        ttl_days=180,
    ),
    "income": PersonaSlot(
        code="income",
        label_ru="Доход",
        value_type=str,
        stable=False,
        extractor_hint="ежемесячный доход собеседника",
        ask_question_triggers=frozenset({"ваш доход", "сколько зарабат"}),
        formatter=_format_str,
        ttl_days=180,
    ),
    "income_type": PersonaSlot(
        code="income_type",
        label_ru="Тип дохода",
        value_type=str,
        stable=False,
        extractor_hint="официально / неофициально / самозанятый / пенсия / нет дохода",
        ask_question_triggers=frozenset({"официально работ", "ваш доход офиц"}),
        formatter=_format_str,
        ttl_days=365,
    ),
    "family_status": PersonaSlot(
        code="family_status",
        label_ru="Семейное положение",
        value_type=str,
        stable=False,
        extractor_hint="женат/замужем/в браке/разведён/холост",
        ask_question_triggers=frozenset({"вы женат", "вы замуж", "вы в браке"}),
        formatter=_format_str,
        ttl_days=365,
    ),
    "children_count": PersonaSlot(
        code="children_count",
        label_ru="Количество детей",
        value_type=int,
        stable=False,  # children are born
        extractor_hint="число детей у собеседника",
        ask_question_triggers=frozenset({"сколько у вас детей"}),
        formatter=_format_int_with_word("ребёнок", "ребёнка", "детей"),
        ttl_days=365 * 2,
    ),
    "property_status": PersonaSlot(
        code="property_status",
        label_ru="Имущество",
        value_type=str,
        stable=False,
        extractor_hint="есть ли квартира/дом/машина у собеседника, может ли быть взыскание имущества",
        ask_question_triggers=frozenset({"ваше имущество", "у вас квартира"}),
        formatter=_format_str,
        ttl_days=180,
    ),
}


# ─── Helpers ────────────────────────────────────────────────────────────────


def get_slot(code: str) -> PersonaSlot | None:
    """Return slot metadata or ``None`` if unknown.

    Unknown slots are NOT auto-registered. The registry is a closed
    vocabulary — adding a slot is a deliberate code change so the
    extractor, policy engine, prompt renderer and admin UI all get
    the new field at the same time.
    """
    return PERSONA_SLOTS.get(code)


def all_slot_codes() -> frozenset[str]:
    """Closed vocabulary the rest of the system iterates over."""
    return frozenset(PERSONA_SLOTS.keys())


def render_facts_block_for_system_prompt(
    confirmed_facts: dict[str, Any] | None,
) -> str:
    """Full Russian block ready to splice into the system prompt.

    Wraps :func:`render_facts_for_prompt` with the header / footer
    instructions ("веди себя как знакомый, ссылайся естественно,
    переспроси если устарело"). Returns "" when there are no facts —
    caller can drop the block entirely without checking length.

    Used by both ``_build_system_prompt`` (non-streaming path) and
    ``generate_response_stream`` (streaming path) so the AI sees
    identical memory context regardless of which LLM provider is
    chosen — preserving call-mode parity.
    """
    inner = render_facts_for_prompt(confirmed_facts, include_stale=True)
    if not inner:
        return ""
    return (
        "═══ ЧТО ТЫ УЖЕ ЗНАЕШЬ О СОБЕСЕДНИКЕ (из прошлых звонков) ═══\n"
        + inner + "\n"
        "═══════════════════════════════════════════════════════════\n"
        "Веди себя как ЗНАКОМЫЙ — не переспрашивай эти данные. Можешь "
        "ССЫЛАТЬСЯ на них естественно («помню, ты говорил про…», "
        "«ты же из <город>?»), но НЕ пересказывать списком. Если факт "
        "помечен «(возможно устарело)» — переспроси аккуратно: "
        "«у тебя всё ещё <X> или что-то изменилось?»."
    )


def render_facts_for_prompt(
    confirmed_facts: dict[str, Any] | None,
    *,
    include_stale: bool = True,
) -> str:
    """Render ``MemoryPersona.confirmed_facts`` into the Russian block
    that ``_build_system_prompt`` injects (TZ-4.5 PR 4).

    Returns an empty string when there are no facts — caller should
    NOT add the surrounding "═══" header in that case (no point
    showing "ЧТО ТЫ ЗНАЕШЬ" with nothing under it).

    Stale facts (past their TTL) are still rendered with a "(возможно
    устарело)" suffix so the AI hedges. Pass ``include_stale=False`` to
    drop them entirely if you ever want a strict-current rendering.
    """
    if not confirmed_facts:
        return ""

    from datetime import datetime, timezone

    lines: list[str] = []
    now = datetime.now(timezone.utc)

    for code, fact in confirmed_facts.items():
        slot = get_slot(code)
        if slot is None:
            # Forward-compat: an old DB row may have a slot we removed.
            # Don't crash, just skip — the audit log still has it.
            continue
        if not isinstance(fact, dict) or "value" not in fact:
            continue
        value = fact["value"]
        try:
            rendered_value = slot.formatter(value)
        except Exception:
            rendered_value = str(value)

        is_stale = False
        if slot.ttl_days is not None and "captured_at" in fact:
            try:
                captured = datetime.fromisoformat(fact["captured_at"])
                if captured.tzinfo is None:
                    captured = captured.replace(tzinfo=timezone.utc)
                age_days = (now - captured).days
                is_stale = age_days > slot.ttl_days
            except (ValueError, TypeError):
                pass

        if is_stale and not include_stale:
            continue

        suffix = " (возможно устарело)" if is_stale else ""
        lines.append(f"  • {slot.label_ru}: {rendered_value}{suffix}")

    return "\n".join(lines)
