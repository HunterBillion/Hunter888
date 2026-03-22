"""Seed script for ~20 narrative + human_factor trap templates.

These are NOT standard Trap model rows — they are JSON template configs
stored in the narrative_trap_detector and human_factor_traps modules.

This seed script inserts them into a `trap_templates` JSONB column on Trap model
with category='narrative' or category='human_factor', and a special
`is_template=True` flag. They don't have static client_phrase/keywords
because they are dynamically generated from ClientStory memory.

Can be run standalone or imported by seed_traps.py.
"""

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings  # noqa: F401
from app.database import async_session, engine, Base
from app.models import *  # noqa: F401,F403
from app.models.roleplay import (
    ArchetypeCode,
    Trap,
    TrapCategory,
)

# UUID namespace (same as seed_traps.py for consistency)
TRAP_NAMESPACE = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


def trap_uuid(code: str) -> uuid.UUID:
    return uuid.uuid5(TRAP_NAMESPACE, code)


# ─────────────────────────────────────────────────────────────────────────
# NARRATIVE TRAP TEMPLATES (12 templates)
# ─────────────────────────────────────────────────────────────────────────

NARRATIVE_TRAP_TEMPLATES = [
    # ─── PROMISE_CHECK (4 templates) ───
    {
        "code": "NT-001",
        "name": "Невыполненное обещание: документы",
        "category": TrapCategory.narrative,
        "subcategory": "promise_check",
        "difficulty": 6,
        "description": "Клиент спрашивает про обещанные документы. Менеджер должен или подтвердить отправку, или объяснить задержку.",
        "template_config": {
            "promise_keywords": ["документы", "бумаги", "справки", "выписки"],
            "severity_base": 0.5,
            "severity_on_fell": 0.7,
            "consequence_type": "credibility_loss",
        },
        "archetype_codes": ["skeptic", "pragmatic", "hostile", "returner"],
        "min_call_number": 2,
        "penalty": -5,
        "bonus": 3,
    },
    {
        "code": "NT-002",
        "name": "Невыполненное обещание: перезвонить",
        "category": TrapCategory.narrative,
        "subcategory": "promise_check",
        "difficulty": 5,
        "description": "Клиент ждал звонка. Менеджер обещал перезвонить и не перезвонил (или перезвонил поздно).",
        "template_config": {
            "promise_keywords": ["перезвонить", "позвонить", "свяжусь", "наберу"],
            "severity_base": 0.4,
            "severity_on_fell": 0.6,
            "consequence_type": "trust_change",
        },
        "archetype_codes": ["anxious", "passive", "avoidant", "rushed"],
        "min_call_number": 2,
        "penalty": -4,
        "bonus": 2,
    },
    {
        "code": "NT-003",
        "name": "Невыполненное обещание: расчёт",
        "category": TrapCategory.narrative,
        "subcategory": "promise_check",
        "difficulty": 7,
        "description": "Клиент просит обещанный расчёт по долгам. Менеджер должен предоставить конкретику.",
        "template_config": {
            "promise_keywords": ["расчёт", "калькуляция", "посчитать", "сумма"],
            "severity_base": 0.6,
            "severity_on_fell": 0.8,
            "consequence_type": "credibility_loss",
        },
        "archetype_codes": ["pragmatic", "know_it_all", "negotiator", "lawyer_client"],
        "min_call_number": 2,
        "penalty": -6,
        "bonus": 4,
    },
    {
        "code": "NT-004",
        "name": "Невыполненное обещание: консультация с юристом",
        "category": TrapCategory.narrative,
        "subcategory": "promise_check",
        "difficulty": 6,
        "description": "Обещали подключить юриста/старшего специалиста — не подключили.",
        "template_config": {
            "promise_keywords": ["юрист", "специалист", "эксперт", "руководитель"],
            "severity_base": 0.5,
            "severity_on_fell": 0.7,
            "consequence_type": "trust_change",
        },
        "archetype_codes": ["skeptic", "delegator", "lawyer_client", "know_it_all"],
        "min_call_number": 3,
        "penalty": -5,
        "bonus": 3,
    },

    # ─── MEMORY_CHECK (4 templates) ───
    {
        "code": "NT-005",
        "name": "Проверка памяти: имя/семья",
        "category": TrapCategory.narrative,
        "subcategory": "memory_check",
        "difficulty": 4,
        "description": "Клиент проверяет, помнит ли менеджер его семейную ситуацию (жена, дети, родители).",
        "template_config": {
            "memory_keys": ["family", "spouse", "children", "dependents"],
            "severity_base": 0.3,
            "severity_on_fell": 0.5,
            "consequence_type": "trust_change",
        },
        "archetype_codes": ["anxious", "grateful", "crying", "overwhelmed", "couple"],
        "min_call_number": 2,
        "penalty": -3,
        "bonus": 4,
    },
    {
        "code": "NT-006",
        "name": "Проверка памяти: сумма долга",
        "category": TrapCategory.narrative,
        "subcategory": "memory_check",
        "difficulty": 5,
        "description": "Клиент ссылается на ранее названную сумму долга. Менеджер должен помнить.",
        "template_config": {
            "memory_keys": ["debt_amount", "total_debt", "credit_sum"],
            "severity_base": 0.4,
            "severity_on_fell": 0.6,
            "consequence_type": "credibility_loss",
        },
        "archetype_codes": ["pragmatic", "know_it_all", "negotiator", "skeptic"],
        "min_call_number": 2,
        "penalty": -4,
        "bonus": 3,
    },
    {
        "code": "NT-007",
        "name": "Проверка памяти: кредитор",
        "category": TrapCategory.narrative,
        "subcategory": "memory_check",
        "difficulty": 5,
        "description": "Клиент упоминает банк-кредитор — менеджер должен помнить какой.",
        "template_config": {
            "memory_keys": ["creditor", "bank", "mfo"],
            "severity_base": 0.4,
            "severity_on_fell": 0.6,
            "consequence_type": "credibility_loss",
        },
        "archetype_codes": ["paranoid", "skeptic", "lawyer_client"],
        "min_call_number": 2,
        "penalty": -4,
        "bonus": 3,
    },
    {
        "code": "NT-008",
        "name": "Проверка памяти: договорённость о встрече",
        "category": TrapCategory.narrative,
        "subcategory": "memory_check",
        "difficulty": 6,
        "description": "Клиент проверяет, помнит ли менеджер договорённость о визите в офис.",
        "template_config": {
            "memory_keys": ["meeting", "office_visit", "appointment"],
            "severity_base": 0.5,
            "severity_on_fell": 0.7,
            "consequence_type": "trust_change",
        },
        "archetype_codes": ["pragmatic", "rushed", "delegator", "passive"],
        "min_call_number": 3,
        "penalty": -5,
        "bonus": 3,
    },

    # ─── CONSISTENCY_CHECK (4 templates) ───
    {
        "code": "NT-009",
        "name": "Проверка консистентности: срок процедуры",
        "category": TrapCategory.narrative,
        "subcategory": "consistency_check",
        "difficulty": 7,
        "description": "Клиент ловит менеджера на противоречии в сроках процедуры банкротства.",
        "template_config": {
            "consistency_field": "procedure_duration",
            "severity_base": 0.6,
            "severity_on_fell": 0.8,  # high — direct contradiction
            "consequence_type": "credibility_loss",
        },
        "archetype_codes": ["know_it_all", "lawyer_client", "skeptic", "manipulator"],
        "min_call_number": 2,
        "penalty": -7,
        "bonus": 5,
    },
    {
        "code": "NT-010",
        "name": "Проверка консистентности: стоимость услуг",
        "category": TrapCategory.narrative,
        "subcategory": "consistency_check",
        "difficulty": 8,
        "description": "Клиент замечает расхождение в стоимости услуг между звонками.",
        "template_config": {
            "consistency_field": "service_cost",
            "severity_base": 0.7,
            "severity_on_fell": 0.9,
            "consequence_type": "credibility_loss",
        },
        "archetype_codes": ["negotiator", "shopper", "skeptic", "paranoid"],
        "min_call_number": 2,
        "penalty": -8,
        "bonus": 5,
    },
    {
        "code": "NT-011",
        "name": "Проверка консистентности: гарантии",
        "category": TrapCategory.narrative,
        "subcategory": "consistency_check",
        "difficulty": 8,
        "description": "Клиент напоминает о гарантиях, которые менеджер давал ранее.",
        "template_config": {
            "consistency_field": "guarantees",
            "severity_base": 0.7,
            "severity_on_fell": 0.9,
            "consequence_type": "trust_change",
        },
        "archetype_codes": ["skeptic", "paranoid", "lawyer_client", "manipulator"],
        "min_call_number": 3,
        "penalty": -8,
        "bonus": 4,
    },
    {
        "code": "NT-012",
        "name": "Проверка консистентности: план действий",
        "category": TrapCategory.narrative,
        "subcategory": "consistency_check",
        "difficulty": 6,
        "description": "Клиент сравнивает текущий план с тем, что обсуждали ранее.",
        "template_config": {
            "consistency_field": "action_plan",
            "severity_base": 0.5,
            "severity_on_fell": 0.7,
            "consequence_type": "credibility_loss",
        },
        "archetype_codes": ["pragmatic", "know_it_all", "delegator"],
        "min_call_number": 2,
        "penalty": -5,
        "bonus": 3,
    },
]


# ─────────────────────────────────────────────────────────────────────────
# HUMAN FACTOR TRAP TEMPLATES (8 templates)
# ─────────────────────────────────────────────────────────────────────────

HUMAN_FACTOR_TRAP_TEMPLATES = [
    # ─── PATIENCE (2 templates) ───
    {
        "code": "HF-001",
        "name": "Терпение: агрессивный клиент",
        "category": TrapCategory.human_factor,
        "subcategory": "patience",
        "difficulty": 6,
        "description": "Клиент-агрессор проверяет терпение. Менеджер НЕ должен давить или отвечать агрессией.",
        "template_config": {
            "required_factor": "patience",
            "fell_triggers": ["pressure", "counter_aggression"],
            "dodged_triggers": ["calm_response", "empathy"],
            "severity_base": 0.6,
        },
        "archetype_codes": ["aggressive", "hostile", "blamer", "sarcastic"],
        "emotion_states": ["hostile", "testing"],
        "penalty": -10,
        "bonus": 5,
    },
    {
        "code": "HF-002",
        "name": "Терпение: повторный вопрос",
        "category": TrapCategory.human_factor,
        "subcategory": "patience",
        "difficulty": 4,
        "description": "Клиент задаёт один вопрос снова и снова. Менеджер должен терпеливо отвечать.",
        "template_config": {
            "required_factor": "patience",
            "fell_triggers": ["pressure", "bad_response"],
            "dodged_triggers": ["acknowledge", "facts", "calm_response"],
            "severity_base": 0.4,
        },
        "archetype_codes": ["anxious", "overwhelmed", "passive", "desperate"],
        "emotion_states": ["guarded", "cold"],
        "penalty": -6,
        "bonus": 3,
    },

    # ─── EMPATHY (2 templates) ───
    {
        "code": "HF-003",
        "name": "Эмпатия: слёзы клиента",
        "category": TrapCategory.human_factor,
        "subcategory": "empathy",
        "difficulty": 5,
        "description": "Клиент плачет. Менеджер должен проявить сочувствие, а не переходить к фактам.",
        "template_config": {
            "required_factor": "empathy",
            "context_triggers": ["resolve_fear"],
            "fell_absent_triggers": ["empathy"],
            "dodged_triggers": ["empathy", "resolve_fear"],
            "severity_base": 0.5,
        },
        "archetype_codes": ["crying", "overwhelmed", "anxious", "desperate"],
        "emotion_states": ["cold", "guarded"],
        "penalty": -8,
        "bonus": 5,
    },
    {
        "code": "HF-004",
        "name": "Эмпатия: страх потери жилья",
        "category": TrapCategory.human_factor,
        "subcategory": "empathy",
        "difficulty": 6,
        "description": "Клиент боится потерять единственное жильё. Нужна поддержка + факты по защите.",
        "template_config": {
            "required_factor": "empathy",
            "context_triggers": ["resolve_fear"],
            "fell_absent_triggers": ["empathy"],
            "dodged_triggers": ["empathy", "facts", "resolve_fear"],
            "severity_base": 0.6,
        },
        "archetype_codes": ["anxious", "paranoid", "couple", "overwhelmed"],
        "emotion_states": ["guarded", "cold", "considering"],
        "penalty": -8,
        "bonus": 6,
    },

    # ─── FLATTERY (2 templates) ───
    {
        "code": "HF-005",
        "name": "Лесть: комплимент → скидка",
        "category": TrapCategory.human_factor,
        "subcategory": "flattery",
        "difficulty": 5,
        "description": "Клиент хвалит менеджера и ждёт поблажек. Скидка = провал.",
        "template_config": {
            "required_factor": "flattery",
            "compliment_context": True,
            "fell_triggers": ["flexible_offer"],
            "dodged_triggers": ["boundary", "facts"],
            "severity_base": 0.4,
        },
        "archetype_codes": ["manipulator", "grateful", "shopper", "negotiator"],
        "emotion_states": ["considering", "negotiating", "deal"],
        "penalty": -7,
        "bonus": 3,
    },
    {
        "code": "HF-006",
        "name": "Лесть: 'вы лучший' → послабление",
        "category": TrapCategory.human_factor,
        "subcategory": "flattery",
        "difficulty": 6,
        "description": "Клиент называет менеджера лучшим и просит исключение из правил.",
        "template_config": {
            "required_factor": "flattery",
            "compliment_context": True,
            "fell_triggers": ["flexible_offer", "acknowledge"],
            "dodged_triggers": ["boundary", "facts"],
            "severity_base": 0.5,
        },
        "archetype_codes": ["manipulator", "sarcastic", "negotiator"],
        "emotion_states": ["considering", "negotiating"],
        "penalty": -7,
        "bonus": 4,
    },

    # ─── URGENCY (2 templates) ───
    {
        "code": "HF-007",
        "name": "Срочность: 'решите прямо сейчас!'",
        "category": TrapCategory.human_factor,
        "subcategory": "urgency",
        "difficulty": 5,
        "description": "Клиент давит срочностью. Менеджер не должен торопиться и давить в ответ.",
        "template_config": {
            "required_factor": "urgency",
            "fell_triggers": ["speed", "pressure"],
            "dodged_triggers": ["honest_uncertainty", "boundary", "calm_response"],
            "severity_base": 0.5,
        },
        "archetype_codes": ["rushed", "aggressive", "desperate", "anxious"],
        "emotion_states": ["hostile", "testing", "cold"],
        "penalty": -6,
        "bonus": 3,
    },
    {
        "code": "HF-008",
        "name": "Срочность: ложные обещания под давлением",
        "category": TrapCategory.human_factor,
        "subcategory": "urgency",
        "difficulty": 7,
        "description": "Клиент требует гарантий прямо сейчас. Менеджер даёт нереалистичные обещания.",
        "template_config": {
            "required_factor": "urgency",
            "fell_triggers": ["speed", "pressure"],
            "dodged_triggers": ["honest_uncertainty", "facts", "boundary"],
            "severity_base": 0.6,
        },
        "archetype_codes": ["rushed", "desperate", "pragmatic", "hostile"],
        "emotion_states": ["hostile", "testing", "negotiating"],
        "penalty": -8,
        "bonus": 4,
    },
]


# ─────────────────────────────────────────────────────────────────────────
# Seeding logic
# ─────────────────────────────────────────────────────────────────────────

async def seed_narrative_traps(db: AsyncSession) -> None:
    """Seed 12 narrative + 8 human_factor trap templates.

    These are stored as Trap rows with:
    - category = 'narrative' or 'human_factor'
    - client_phrase = None (dynamic traps, no static phrase)
    - detection_config JSONB = template_config
    """
    all_templates = NARRATIVE_TRAP_TEMPLATES + HUMAN_FACTOR_TRAP_TEMPLATES

    traps = []
    for t in all_templates:
        trap = Trap(
            id=trap_uuid(t["code"]),
            code=t["code"],
            name=t["name"],
            category=t["category"],
            subcategory=t.get("subcategory", ""),
            difficulty=t["difficulty"],
            # Narrative/HF traps have no static client phrase
            client_phrase=t.get("description", ""),
            client_phrase_variants=[],
            wrong_response_keywords=[],
            correct_response_keywords=[],
            wrong_response_example="",
            correct_response_example="",
            explanation=t.get("description", ""),
            law_reference="",
            archetype_codes=t.get("archetype_codes", []),
            emotion_states=t.get("emotion_states", []),
            penalty=t.get("penalty", -5),
            bonus=t.get("bonus", 3),
            fell_emotion_trigger="",
            dodged_emotion_trigger="",
            detection_config=t.get("template_config", {}),
            min_call_number=t.get("min_call_number", 1),
            is_active=True,
        )
        traps.append(trap)

    db.add_all(traps)
    await db.flush()
    print(f"  Narrative/HF trap templates: {len(traps)} created "
          f"({len(NARRATIVE_TRAP_TEMPLATES)} narrative + {len(HUMAN_FACTOR_TRAP_TEMPLATES)} human_factor)")


async def seed() -> None:
    """Main entry point: seed narrative + human factor traps."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        print("Seeding narrative & human factor trap templates...")
        await seed_narrative_traps(db)
        await db.commit()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())
