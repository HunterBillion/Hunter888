"""Tier B case generation — skeleton + LLM slot fill.

Produces a QuizCase by:
  1. Picking a skeleton matching (complexity, user_level).
  2. Randomly sampling slot values (business_type, trigger, occupation, amount).
  3. Calling a SMALL LLM (task_type='structured', local preferred) to generate:
     - debtor full_name
     - narrative_hook (1-2 sentences in character)
  4. Assembling creditors from templates with random amounts.
  5. Returning a QuizCase with source_tier="B".

Latency budget: 1-2s (navy.api claude-sonnet-4.6 structured task ~1s, Ollama
local ~1.5s). Much cheaper than Tier C full generation.

Falls back to Tier A (seed) if LLM fails — returns None and caller retries.
"""

from __future__ import annotations

import json
import logging
import random
import re
import uuid
from pathlib import Path
from typing import Literal

from app.services.quiz_v2.cases import QuizCase

logger = logging.getLogger(__name__)

_SKELETONS_PATH = Path(__file__).resolve().parent / "skeletons_seed.json"
_SKELETONS_CACHE: list[dict] | None = None


def _load_skeletons() -> list[dict]:
    global _SKELETONS_CACHE
    if _SKELETONS_CACHE is not None:
        return _SKELETONS_CACHE
    try:
        data = json.loads(_SKELETONS_PATH.read_text(encoding="utf-8"))
        _SKELETONS_CACHE = data.get("skeletons", [])
        logger.info("quiz_v2.tier_b: loaded %d skeletons", len(_SKELETONS_CACHE))
        return _SKELETONS_CACHE
    except Exception as exc:
        logger.error("quiz_v2.tier_b: failed to load skeletons: %s", exc)
        _SKELETONS_CACHE = []
        return []


def _pick_skeleton(complexity: Literal["simple", "tangled", "adversarial"]) -> dict | None:
    skeletons = [s for s in _load_skeletons() if s.get("complexity") == complexity]
    if not skeletons:
        return None
    return random.choice(skeletons)


def _sample_amount(debt_range: list[int]) -> int:
    """Pick a realistic round debt amount from the range."""
    lo, hi = debt_range
    raw = random.randint(lo, hi)
    # Round to nearest 10k for realism (real debts aren't "523_174")
    return round(raw / 10_000) * 10_000


def _distribute_amount(total: int, n_parts: int) -> list[int]:
    """Split total into n_parts, biased so first creditor is largest."""
    if n_parts <= 0:
        return []
    if n_parts == 1:
        return [total]
    # Weighted split: [0.5, 0.25, 0.15, 0.10, ...] descending
    weights = [1.0 / (i + 1.5) for i in range(n_parts)]
    ws = sum(weights)
    parts = [int(total * w / ws / 10_000) * 10_000 for w in weights]
    # Fix rounding drift — put remainder on first
    diff = total - sum(parts)
    if parts:
        parts[0] += diff
    return parts


def _fill_creditor_template(template: str, amounts: list[int]) -> str:
    """Replace {amt1}, {amt2}, ... in template with amounts (in thousands)."""
    result = template
    for i, amt in enumerate(amounts, start=1):
        result = result.replace(f"{{amt{i}}}", str(amt // 1000))
    # Remove any unfilled {amtN} placeholders
    result = re.sub(r"\{amt\d+\}", "", result)
    return result.strip()


async def _llm_fill_name_and_hook(
    skeleton: dict,
    debtor_age: int,
    debtor_occupation: str,
    trigger: str,
    debt_human: str,
    complexity: str,
) -> tuple[str, str]:
    """Call small LLM to produce full_name + narrative_hook.

    2026-04-18: grounded with real 127-FZ RAG snippets so narrative_hook
    doesn't cite fabricated articles.

    Returns ('Иван Петрович Крылов', '2-sentence hook') or fallback on failure.
    """
    from app.services.llm import generate_response
    from app.services.quiz_v2.rag_grounding import build_rag_grounded_prompt_suffix

    # Pull allowed-articles RAG context
    rag_suffix, _ = await build_rag_grounded_prompt_suffix(
        complexity, max_snippets=3, max_chars_per_snippet=220,
    )

    pattern = skeleton.get("pattern_name", "")
    prompt = (
        f"Сгенерируй данные клиента-должника для учебного кейса по 127-ФЗ.\n\n"
        f"Паттерн: {pattern}\n"
        f"Возраст: {debtor_age}. Род занятий: {debtor_occupation}.\n"
        f"Триггер долга: {trigger}. Сумма долга: {debt_human}.\n\n"
        f"Верни СТРОГО JSON:\n"
        f'{{"full_name": "ФИО в именительном падеже (рус.)", '
        f'"narrative_hook": "1-2 предложения — описание ключевой проблемы дела"}}\n\n'
        f"Имя должно быть реалистичным русским (Иван Петрович Крылов, "
        f"Анна Викторовна Соколова). Без клише (Иванов Иван Иванович).\n"
        f"narrative_hook может ссылаться на статью ТОЛЬКО из правового контекста ниже.\n"
        f"{rag_suffix}"
    )
    try:
        result = await generate_response(
            system_prompt="Ты генератор учебных кейсов по законодательству о банкротстве РФ.",
            messages=[{"role": "user", "content": prompt}],
            emotion_state="curious",
            task_type="structured",
            prefer_provider="cloud",
        )
        # Extract JSON from response
        content = result.content.strip()
        # Try to find JSON block
        m = re.search(r"\{[^{}]*\"full_name\"[^{}]*\}", content, re.DOTALL)
        if m:
            parsed = json.loads(m.group(0))
            name = (parsed.get("full_name") or "").strip()
            hook = (parsed.get("narrative_hook") or "").strip()
            if name and hook:
                return name, hook
    except Exception as exc:
        logger.warning("quiz_v2.tier_b: LLM fill failed: %s", exc)

    # Fallback: hardcoded name pool + skeleton narrative_template
    fallback_names = [
        "Александр Викторович Орлов", "Мария Дмитриевна Белая",
        "Сергей Павлович Гришин", "Елена Юрьевна Мержоева",
        "Дмитрий Николаевич Шатов", "Татьяна Сергеевна Каплан",
        "Андрей Олегович Сотников", "Ольга Михайловна Третьякова",
    ]
    fallback_hook = skeleton.get("narrative_template", "Учебный кейс по 127-ФЗ.")
    return random.choice(fallback_names), fallback_hook


async def generate_tier_b_case(
    *,
    complexity: Literal["simple", "tangled", "adversarial"],
) -> QuizCase | None:
    """Generate a fresh QuizCase via Tier B skeleton + LLM slot fill.

    Returns None if no skeleton matches or LLM path completely fails — caller
    falls back to Tier A.
    """
    skeleton = _pick_skeleton(complexity)
    if not skeleton:
        return None

    # ── Sample slots ────────────────────────────────────────────────────────
    age_lo, age_hi = skeleton.get("debtor_age_range", [30, 55])
    debtor_age = random.randint(age_lo, age_hi)
    debt = _sample_amount(skeleton.get("debt_amount_range", [500_000, 1_500_000]))
    trigger = random.choice(skeleton.get("trigger_events", ["неплатёжеспособность"]))

    # Occupation / business_type — simple skeleton has "business_types", others "occupations"
    occupation_pool = skeleton.get("business_types") or skeleton.get("occupations") or ["сотрудник"]
    debtor_occupation = random.choice(occupation_pool)
    if "business_types" in skeleton:
        debtor_occupation = f"бывший ИП, {debtor_occupation}"

    # ── Distribute debt across 2-4 creditors ────────────────────────────────
    creditor_templates = skeleton.get("creditor_templates", [])
    n_creditors = min(len(creditor_templates), random.randint(2, 4))
    picked_templates = random.sample(creditor_templates, n_creditors) if n_creditors > 0 else []
    # For each template: sample a random "amount slot" — template may have {amt1}, {amt2}...
    # We just distribute total debt.
    part_amounts = _distribute_amount(debt, n_creditors)
    creditors = [
        _fill_creditor_template(tpl, [amt])
        for tpl, amt in zip(picked_templates, part_amounts)
    ]
    # Drop empties
    creditors = [c for c in creditors if c]

    # ── Human-readable amount for prompt ────────────────────────────────────
    if debt >= 1_000_000:
        debt_human = f"{debt / 1_000_000:.1f} млн ₽".replace(".0 ", " ")
    else:
        debt_human = f"{debt // 1000} тыс. ₽"

    # ── LLM fill: name + narrative_hook (RAG-grounded) ──────────────────────
    full_name, narrative_hook = await _llm_fill_name_and_hook(
        skeleton, debtor_age, debtor_occupation, trigger, debt_human, complexity,
    )

    # ── Assemble QuizCase ───────────────────────────────────────────────────
    # Complicating factors — none for tier B by default (simple skeletons);
    # tangled/adversarial can include 1-2 if skeleton has them.
    complicating = []
    if complexity in ("tangled", "adversarial"):
        # Pick 1-2 from trigger_events pool excluding chosen trigger
        others = [t for t in skeleton.get("trigger_events", []) if t != trigger]
        if others:
            complicating = random.sample(others, min(len(others), random.randint(1, 2)))

    case_id = f"B-{skeleton.get('skeleton_id', 'SX').split('-')[1]}-{uuid.uuid4().hex[:6]}"

    case = QuizCase(
        case_id=case_id,
        complexity=complexity,
        debtor_name=full_name,
        debtor_age=debtor_age,
        debtor_occupation=debtor_occupation,
        debt_amount=debt,
        creditors=creditors,
        trigger_event=trigger,
        complicating_factors=complicating,
        narrative_hook=narrative_hook,
        expected_beats=skeleton.get("expected_beats", {}),
        source_tier="B",
    )
    logger.info(
        "quiz_v2.tier_b: generated case=%s skeleton=%s name=%s debt=%d",
        case_id, skeleton.get("skeleton_id"), full_name, debt,
    )
    return case
