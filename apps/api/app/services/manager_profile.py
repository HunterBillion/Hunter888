"""Manager profile memory — extract and inject manager's own name/company.

Problem: the AI client used to forget who is calling. The manager would say
"Меня зовут Дмитрий из ЮрИнвест", and three turns later the AI would ask
"а как вас зовут?" or refer to them as "менеджер". Terrible.

Solution (Phase 2.4, 2026-04-18):

1. **Extraction.** After every user turn, run ``extract_manager_identity`` on
   the content. It pattern-matches common self-introductions in Russian —
   "меня зовут X из Y", "это X Y из компании Z", etc. — and returns a
   normalised ``ManagerIdentity`` if confident.
2. **Persistence.** The WS-layer writes each new extraction to
   ``EpisodicMemory`` (``memory_type="entity"``) with ``salience=1.0`` so
   it survives call-to-call compression.
3. **Injection.** Before every LLM turn, the service reads the most recent
   entity memories for the story and produces a short
   ``## ПРОФИЛЬ МЕНЕДЖЕРА`` section. Goes into the system prompt alongside
   the existing sections.

Injection is additive and optional — if no identity has been captured yet,
``build_manager_profile_section`` returns an empty string and nothing changes.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Extraction
# ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ManagerIdentity:
    """Resolved manager identity extracted from a user turn.

    All fields optional — we store whatever matched. Confidence is a rough
    heuristic [0.0-1.0]; the calling code can ignore low-confidence hits
    (e.g. when only a first-name was inferred and the turn is dominated by
    questions from the client).
    """

    name: Optional[str] = None
    surname: Optional[str] = None
    company: Optional[str] = None
    raw_match: Optional[str] = None
    confidence: float = 0.0

    def is_empty(self) -> bool:
        return not (self.name or self.company)


# Patterns are ordered from most specific to least. First match wins.
#
# NOTE: we do NOT use ``re.IGNORECASE`` on the whole pattern — that would
# let lowercase pronouns like "вас", "меня", "нас" get captured as names by
# ``[А-ЯЁ]``. Instead, the trigger keywords ("меня зовут", "это", "говорит")
# are written both lowercase AND with explicit alternation where needed,
# and captured name/surname groups REQUIRE the first letter to be capitalised
# (``[А-ЯЁ]`` without IGNORECASE).
_NAME_WORD = r"([А-ЯЁ][а-яёА-ЯЁ]{1,19})"
_SURNAME_WORD = r"([А-ЯЁ][а-яёА-ЯЁ]{1,24})"
_COMPANY_TAIL = r"(?:[«\"]\s*)?([А-ЯЁA-Z][\w\s\-«»\"'.]{2,60}?)(?:[»\"]|[\s,.!?]|$)"

# ``(?i:...)`` applies case-insensitivity ONLY to the trigger verbs.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # "Меня зовут Дмитрий Иванов[,] из [компании] ЮрИнвест"
    # "Моё имя Анна[,] [я] из ЮрПомощь"
    (
        re.compile(
            rf"(?i:меня\s+зовут|моё\s+имя)\s+{_NAME_WORD}"
            rf"(?:\s+{_SURNAME_WORD})?"
            rf"(?:\s*[,]?\s*(?:(?i:я\s+)?(?i:из|от))\s+(?:(?i:компании)\s+)?{_COMPANY_TAIL})?",
        ),
        "named_self_intro",
    ),
    # "Это Дмитрий из ЮрИнвест", "Говорит Мария из X"
    (
        re.compile(
            rf"(?i:это|говорит|здравствуйте,?)\s+{_NAME_WORD}"
            rf"(?:\s+{_SURNAME_WORD})?"
            rf"\s+(?i:из|от|беспокоит\s+(?:из|от))\s+(?:(?i:компании)\s+)?{_COMPANY_TAIL}",
        ),
        "greeting_with_company",
    ),
    # "Иван Петров из компании Правовед"
    (
        re.compile(
            rf"^{_NAME_WORD}\s+{_SURNAME_WORD}\s+(?i:из)\s+(?:(?i:компании)\s+)?{_COMPANY_TAIL}",
            re.MULTILINE,
        ),
        "positional",
    ),
    # "Алло, это Пётр." — name-only fallback, low confidence.
    (
        re.compile(
            rf"(?i:алло[,.]?\s+)?(?i:это|говорит|здравствуйте,?)\s+{_NAME_WORD}"
            rf"(?:[,.!?]|\s|$)",
        ),
        "name_only",
    ),
]

# Confidence heuristic per pattern name.
_CONFIDENCE_BY_PATTERN: dict[str, float] = {
    "named_self_intro": 0.95,
    "greeting_with_company": 0.92,
    "positional": 0.80,
    "name_only": 0.60,
}

# Обычные русские имена — фильтр от ложных срабатываний ("Добрый" как имя).
_NOT_A_NAME = {
    "Добрый", "Здравствуйте", "Алло", "Слушаю", "Извините", "Простите",
    "Скажите", "Подождите", "Клиент", "Менеджер", "Помогите", "Объясните",
    "Банкрот", "Должник", "Компания", "Россия",
    # Pronouns & common beginners that case-insensitive regex could catch.
    "Вас", "Вам", "Вы", "Меня", "Мне", "Мы", "Нас", "Нам",
    "Он", "Она", "Они", "Ты", "Тебя",
}


def extract_manager_identity(text: str) -> ManagerIdentity | None:
    """Return the best ``ManagerIdentity`` from a single user turn or None.

    Called from the WS layer on every inbound user message. ``None`` means
    the text didn't contain a recognisable self-introduction — the caller
    simply skips persistence.
    """

    if not text or len(text) < 4:
        return None

    for pattern, name in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        groups = m.groups()
        first = (groups[0] or "").strip() if groups else ""
        surname = (groups[1] or "").strip() if len(groups) > 1 else ""
        company = (groups[2] or "").strip() if len(groups) > 2 else ""

        if first and first in _NOT_A_NAME:
            continue
        if surname in _NOT_A_NAME:
            surname = ""

        company = company.strip(" «»\"'.,")
        # "name_only" pattern must produce a real name to be useful.
        if name == "name_only" and (not first or len(first) < 2):
            continue

        ident = ManagerIdentity(
            name=first or None,
            surname=surname or None,
            company=company or None,
            raw_match=m.group(0)[:200],
            confidence=_CONFIDENCE_BY_PATTERN.get(name, 0.5),
        )
        if ident.is_empty():
            continue
        logger.debug("manager_profile: extracted %s via %s", ident, name)
        return ident

    return None


# ────────────────────────────────────────────────────────────────────
# Persistence
# ────────────────────────────────────────────────────────────────────


_ENTITY_MEMORY_TYPE = "entity"
_ENTITY_KEY_NAME = "manager_name"
_ENTITY_KEY_COMPANY = "manager_company"


async def persist_manager_identity(
    *,
    story_id: uuid.UUID | str | None,
    session_id: uuid.UUID | str,
    call_number: int,
    identity: ManagerIdentity,
    db: AsyncSession,
) -> None:
    """Upsert one ``EpisodicMemory(memory_type="entity")`` row per field.

    We don't dedupe aggressively — if the manager re-introduces themselves
    with a different name we want both in history, and the newer one wins
    because ``build_manager_profile_section`` orders by ``created_at DESC``.
    Only a handful of rows are expected per story, so this is cheap.
    """

    if identity.is_empty() or not story_id:
        return

    from app.models.roleplay import EpisodicMemory

    rows: list[EpisodicMemory] = []

    def _mk(key: str, value: str) -> EpisodicMemory:
        return EpisodicMemory(
            story_id=uuid.UUID(str(story_id)),
            session_id=uuid.UUID(str(session_id)),
            call_number=call_number,
            memory_type=_ENTITY_MEMORY_TYPE,
            content=f"{key}={value}",
            salience=max(1, min(10, int(round(identity.confidence * 10)))),
            valence=0.0,
            is_compressed=False,
            token_count=max(1, len(value) // 4),
        )

    if identity.name:
        full_name = (
            f"{identity.name} {identity.surname}".strip()
            if identity.surname
            else identity.name
        )
        rows.append(_mk(_ENTITY_KEY_NAME, full_name))
    if identity.company:
        rows.append(_mk(_ENTITY_KEY_COMPANY, identity.company))

    for row in rows:
        db.add(row)
    try:
        await db.flush()
        logger.info(
            "manager_profile: persisted %d entity memories for story=%s "
            "session=%s name=%r company=%r",
            len(rows), story_id, session_id, identity.name, identity.company,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("manager_profile: persist failed: %s", exc)


# ────────────────────────────────────────────────────────────────────
# Injection into LLM prompt
# ────────────────────────────────────────────────────────────────────


async def build_manager_profile_section(
    *,
    story_id: uuid.UUID | str | None,
    db: AsyncSession,
) -> str:
    """Return a ``## ПРОФИЛЬ МЕНЕДЖЕРА`` prompt fragment, or ``""`` if empty.

    Reads the newest ``entity`` memories for the story and produces a
    ~200-token block the client LLM can use to address the manager by name.
    """

    if not story_id:
        return ""

    from app.models.roleplay import EpisodicMemory

    try:
        result = await db.execute(
            select(EpisodicMemory)
            .where(EpisodicMemory.story_id == uuid.UUID(str(story_id)))
            .where(EpisodicMemory.memory_type == _ENTITY_MEMORY_TYPE)
            .order_by(EpisodicMemory.created_at.desc())
            .limit(20)
        )
        rows = list(result.scalars().all())
    except Exception as exc:  # noqa: BLE001
        logger.warning("manager_profile: select failed: %s", exc)
        return ""

    if not rows:
        return ""

    name: str | None = None
    company: str | None = None
    for row in rows:
        if row.content.startswith(f"{_ENTITY_KEY_NAME}="):
            if name is None:
                name = row.content.split("=", 1)[1].strip()
        elif row.content.startswith(f"{_ENTITY_KEY_COMPANY}="):
            if company is None:
                company = row.content.split("=", 1)[1].strip()

    if not name and not company:
        return ""

    lines = ["## ПРОФИЛЬ МЕНЕДЖЕРА"]
    if name:
        lines.append(f"Имя: {name}")
    if company:
        lines.append(f"Компания: {company}")
    lines.append(
        "Используй имя естественно 1-2 раза за звонок (не в каждой фразе). "
        "Если менеджер представился — не спрашивай имя повторно."
    )
    return "\n".join(lines) + "\n"
