"""Personality RAG — lorebook entry retrieval for character archetypes.

Replaces monolithic 25K character prompt files with dynamic context injection.
Two retrieval strategies:
  1. Keyword matching (regex, 0ms) — primary, for common triggers
  2. Embedding similarity (pgvector, ~50ms) — fallback when keywords miss

Architecture follows rag_legal.py patterns for consistency.
"""

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.rag import PersonalityChunk, PersonalityExample, TraitCategory

logger = logging.getLogger(__name__)


# ─── Data structures ─────────────────────────────────────────────────────────


@dataclass
class LorebookEntry:
    """A single retrieved lorebook entry."""
    chunk_id: str
    trait_category: str
    content: str
    priority: int
    trigger_method: str  # "keyword" | "embedding" | "always"
    relevance_score: float = 1.0


@dataclass
class RetrievedExample:
    """A few-shot dialogue example retrieved by semantic similarity."""
    situation: str
    dialogue: str
    emotion: str | None = None
    relevance_score: float = 0.0


@dataclass
class LorebookContext:
    """Complete lorebook context for one prompt assembly."""
    archetype_code: str
    character_card: str  # Always-loaded core identity
    entries: list[LorebookEntry] = field(default_factory=list)
    examples: list[RetrievedExample] = field(default_factory=list)
    total_tokens_estimate: int = 0

    def to_prompt_sections(self) -> list[str]:
        """Convert to prompt sections for assembly."""
        sections = []

        # Character card is always first
        if self.character_card:
            sections.append(self.character_card)

        # Lorebook entries sorted by priority (highest first)
        if self.entries:
            entry_texts = [e.content for e in sorted(self.entries, key=lambda x: -x.priority)]
            sections.append("\n\n".join(entry_texts))

        # Few-shot examples
        if self.examples:
            lines = ["Вот как этот персонаж обычно реагирует:"]
            for ex in self.examples:
                lines.append(f"\nСитуация: {ex.situation}")
                lines.append(f"Персонаж: \"{ex.dialogue}\"")
            sections.append("\n".join(lines))

        return sections


# ─── Keyword retrieval (primary, 0ms) ────────────────────────────────────────


async def retrieve_by_keywords(
    archetype_code: str,
    user_message: str,
    db: AsyncSession,
    max_tokens: int = 400,
) -> list[LorebookEntry]:
    """Retrieve lorebook entries triggered by keywords in user message.

    Fast regex-based matching. Returns entries sorted by priority,
    capped at max_tokens budget.
    """
    message_lower = user_message.lower()

    # Load all active entries for this archetype
    result = await db.execute(
        select(PersonalityChunk).where(
            and_(
                PersonalityChunk.archetype_code == archetype_code,
                PersonalityChunk.is_active.is_(True),
                PersonalityChunk.trait_category != TraitCategory.core_identity,  # card loaded separately
            )
        ).order_by(PersonalityChunk.priority.desc())
    )
    all_entries = result.scalars().all()

    triggered = []
    for chunk in all_entries:
        keywords = chunk.keywords or []
        if any(kw.lower() in message_lower for kw in keywords):
            triggered.append(LorebookEntry(
                chunk_id=str(chunk.id),
                trait_category=chunk.trait_category.value,
                content=chunk.content,
                priority=chunk.priority,
                trigger_method="keyword",
            ))

    # Budget cap: estimate tokens as len(content) // 2
    budget_used = 0
    capped = []
    for entry in triggered:
        entry_tokens = len(entry.content) // 2
        if budget_used + entry_tokens <= max_tokens:
            capped.append(entry)
            budget_used += entry_tokens
        else:
            break  # Already sorted by priority, so we drop lowest first

    return capped


# ─── Embedding retrieval (fallback) ──────────────────────────────────────────


async def retrieve_by_embedding(
    archetype_code: str,
    user_message: str,
    db: AsyncSession,
    top_k: int = 3,
) -> list[LorebookEntry]:
    """Retrieve lorebook entries by semantic similarity (pgvector).

    Used as fallback when keyword matching returns nothing.
    Requires pre-computed embeddings in PersonalityChunk.embedding.
    """
    from app.services.llm import get_embedding

    try:
        query_embedding = await get_embedding(user_message)
    except Exception as e:
        logger.debug("Embedding retrieval failed (no embedding model): %s", e)
        return []

    if not query_embedding:
        return []

    # Cosine similarity search via pgvector
    result = await db.execute(
        select(PersonalityChunk)
        .where(
            and_(
                PersonalityChunk.archetype_code == archetype_code,
                PersonalityChunk.is_active.is_(True),
                PersonalityChunk.embedding.isnot(None),
                PersonalityChunk.trait_category != TraitCategory.core_identity,
            )
        )
        .order_by(PersonalityChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    chunks = result.scalars().all()

    return [
        LorebookEntry(
            chunk_id=str(c.id),
            trait_category=c.trait_category.value,
            content=c.content,
            priority=c.priority,
            trigger_method="embedding",
        )
        for c in chunks
    ]


# ─── Example retrieval (few-shot RAG) ────────────────────────────────────────


async def retrieve_examples(
    archetype_code: str,
    user_message: str,
    db: AsyncSession,
    top_k: int = 3,
) -> list[RetrievedExample]:
    """Retrieve few-shot dialogue examples by semantic similarity.

    Returns the most relevant examples of how this character speaks
    in situations similar to the current user message.
    """
    from app.services.llm import get_embedding

    try:
        query_embedding = await get_embedding(user_message)
    except Exception:
        logger.debug("Example embedding failed, returning empty")
        return []

    if not query_embedding:
        return []

    result = await db.execute(
        select(PersonalityExample)
        .where(
            and_(
                PersonalityExample.archetype_code == archetype_code,
                PersonalityExample.is_active.is_(True),
                PersonalityExample.embedding.isnot(None),
            )
        )
        .order_by(PersonalityExample.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    examples = result.scalars().all()

    return [
        RetrievedExample(
            situation=ex.situation,
            dialogue=ex.dialogue,
            emotion=ex.emotion,
        )
        for ex in examples
    ]


# ─── Character card retrieval ────────────────────────────────────────────────


async def get_character_card(archetype_code: str, db: AsyncSession) -> str:
    """Load the always-present character card (core_identity entry)."""
    result = await db.execute(
        select(PersonalityChunk.content).where(
            and_(
                PersonalityChunk.archetype_code == archetype_code,
                PersonalityChunk.trait_category == TraitCategory.core_identity,
                PersonalityChunk.is_active.is_(True),
            )
        ).limit(1)
    )
    row = result.scalar_one_or_none()
    return row or ""


# ─── Main retrieval function ─────────────────────────────────────────────────


async def retrieve_lorebook_context(
    archetype_code: str,
    user_message: str,
    db: AsyncSession,
    emotion_state: str = "cold",
) -> LorebookContext:
    """Retrieve complete lorebook context for prompt assembly.

    Strategy:
      1. Always load character card (core_identity)
      2. Keyword-match lorebook entries from user message
      3. If no keywords matched → fallback to embedding similarity
      4. Retrieve few-shot RAG examples by semantic similarity

    Returns LorebookContext with all sections ready for prompt assembly.
    """
    max_entry_tokens = settings.lorebook_max_entry_tokens
    max_examples = settings.lorebook_max_examples

    # 1. Character card (always)
    card = await get_character_card(archetype_code, db)

    # 2. Keyword-triggered entries
    entries = await retrieve_by_keywords(archetype_code, user_message, db, max_tokens=max_entry_tokens)

    # 3. Fallback to embedding if keywords missed
    if not entries:
        entries = await retrieve_by_embedding(archetype_code, user_message, db, top_k=3)
        # Cap by budget
        budget_used = 0
        capped = []
        for e in entries:
            t = len(e.content) // 2
            if budget_used + t <= max_entry_tokens:
                capped.append(e)
                budget_used += t
        entries = capped

    # 4. Few-shot examples
    examples = await retrieve_examples(archetype_code, user_message, db, top_k=max_examples)

    # Estimate total tokens
    total = len(card) // 2
    total += sum(len(e.content) // 2 for e in entries)
    total += sum((len(ex.situation) + len(ex.dialogue)) // 2 for ex in examples)

    logger.debug(
        "Lorebook [%s]: card=%d tok, entries=%d (%d tok), examples=%d (~%d tok total)",
        archetype_code,
        len(card) // 2,
        len(entries),
        sum(len(e.content) // 2 for e in entries),
        len(examples),
        total,
    )

    return LorebookContext(
        archetype_code=archetype_code,
        character_card=card,
        entries=entries,
        examples=examples,
        total_tokens_estimate=total,
    )
