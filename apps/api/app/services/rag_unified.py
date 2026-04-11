"""
Unified RAG — single entry point for all 3 RAG sources (Task 2.4).

Calls Legal, Personality, and Wiki RAG in parallel.
Merges results with context-dependent token budgets.
Respects 8K model constraint: total RAG budget = 1500 tokens.

Usage:
    result = await retrieve_all_context(
        query="Как обработать возражение про цену?",
        user_id=manager_uuid,
        db=db,
        context_type="training",
        archetype_code="skeptic",       # for personality RAG
        emotion_state="guarded",        # for personality RAG
    )
    prompt_text = result.to_prompt()    # formatted for system prompt injection
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ─── Token budgets per context type ─────────────────────────────────────────
# Total: 1500 tokens (conservative for 8K Gemma context)
# CHARS_PER_TOKEN ≈ 2 for Russian text

BUDGET = {
    "training": {"legal": 800, "personality": 400, "wiki": 300},
    "coach":    {"legal": 600, "personality": 200, "wiki": 500},
    "quiz":     {"legal": 1000, "personality": 0, "wiki": 200},
}

CHARS_PER_TOKEN = 2


def _trim(text: str, max_tokens: int) -> str:
    """Trim text to token budget, cutting at last sentence boundary."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    # Find last period within budget
    cut = text[:max_chars].rfind(".")
    if cut > max_chars // 2:
        return text[: cut + 1]
    return text[:max_chars] + "…"


# ─── Result dataclass ───────────────────────────────────────────────────────


@dataclass
class UnifiedRAGResult:
    """Merged RAG result from all sources."""

    legal_context: str = ""
    personality_context: str = ""
    wiki_context: str = ""
    legal_chunks_count: int = 0
    personality_entries_count: int = 0
    wiki_pages_count: int = 0
    total_tokens_estimate: int = 0
    retrieval_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def has_legal(self) -> bool:
        return bool(self.legal_context)

    @property
    def has_wiki(self) -> bool:
        return bool(self.wiki_context)

    def to_prompt(self) -> str:
        """Format all RAG context for system prompt injection."""
        parts: list[str] = []

        if self.legal_context:
            parts.append(
                "ПРАВОВАЯ БАЗА (127-ФЗ):\n" + self.legal_context
            )

        if self.wiki_context:
            parts.append(
                "ПЕРСОНАЛЬНАЯ WIKI МЕНЕДЖЕРА:\n" + self.wiki_context
            )

        # Personality goes through lorebook system, not here
        # (it's assembled separately in llm.py)

        if not parts:
            return ""

        return "\n\n".join(parts)


# ─── Main function ──────────────────────────────────────────────────────────


async def retrieve_all_context(
    query: str,
    user_id: UUID,
    db: AsyncSession,
    context_type: str = "training",
    *,
    archetype_code: str | None = None,
    emotion_state: str = "cold",
) -> UnifiedRAGResult:
    """
    Retrieve context from all 3 RAG sources in parallel.

    Args:
        query: Search query (user message or scenario description)
        user_id: Manager's user ID (for Wiki RAG personalization)
        db: Database session
        context_type: "training" | "coach" | "quiz" — determines token weights
        archetype_code: For Personality RAG (optional, only for training)
        emotion_state: For Personality RAG (optional)

    Returns:
        UnifiedRAGResult with formatted context and metadata
    """
    import time

    start = time.perf_counter()
    budgets = BUDGET.get(context_type, BUDGET["training"])
    result = UnifiedRAGResult()

    # ── Build async tasks ──

    tasks: dict[str, asyncio.Task] = {}

    # Legal RAG
    if budgets["legal"] > 0:

        async def _legal():
            from app.database import async_session as _make_session
            from app.services.rag_legal import retrieve_legal_context, RetrievalConfig

            top_k = 3 if budgets["legal"] <= 600 else 5
            config = RetrievalConfig(top_k=top_k, mode="free_dialog")
            async with _make_session() as rag_db:
                return await retrieve_legal_context(query, rag_db, config=config)

        tasks["legal"] = asyncio.create_task(_legal())

    # Wiki RAG
    if budgets["wiki"] > 0:

        async def _wiki():
            from app.database import async_session as _make_session
            from app.services.rag_wiki import retrieve_wiki_context

            async with _make_session() as rag_db:
                return await retrieve_wiki_context(
                    query, user_id, rag_db, top_k=3, min_similarity=0.20
                )

        tasks["wiki"] = asyncio.create_task(_wiki())

    # Personality RAG (only if archetype provided and budget > 0)
    if budgets["personality"] > 0 and archetype_code:

        async def _personality():
            from app.database import async_session as _make_session
            from app.services.rag_personality import retrieve_lorebook_context

            async with _make_session() as rag_db:
                return await retrieve_lorebook_context(
                    archetype_code=archetype_code,
                    user_message=query,
                    db=rag_db,
                    emotion_state=emotion_state,
                )

        tasks["personality"] = asyncio.create_task(_personality())

    # ── Await all in parallel ──

    for name, task in tasks.items():
        try:
            raw = await task

            if name == "legal":
                if hasattr(raw, "has_results") and raw.has_results:
                    text = raw.to_prompt_context()
                    result.legal_context = _trim(text, budgets["legal"])
                    result.legal_chunks_count = len(raw.results)

            elif name == "wiki":
                if raw:  # list[dict]
                    lines = [
                        f"- [{r['page_path']}]: {r['content'][:200]}"
                        for r in raw
                        if r.get("content")
                    ]
                    if lines:
                        text = "\n".join(lines)
                        result.wiki_context = _trim(text, budgets["wiki"])
                        result.wiki_pages_count = len(lines)

            elif name == "personality":
                if hasattr(raw, "entries") and raw.entries:
                    # Character card is handled by llm.py lorebook assembly.
                    # Here we only extract entries text for non-lorebook consumers (Coach).
                    entry_texts = [e.content for e in raw.entries[:5]]
                    if entry_texts:
                        text = "\n".join(f"- {t}" for t in entry_texts)
                        result.personality_context = _trim(
                            text, budgets["personality"]
                        )
                        result.personality_entries_count = len(entry_texts)

        except Exception as exc:
            logger.warning("Unified RAG [%s] failed: %s", name, exc)
            result.errors.append(f"{name}: {exc}")

    # ── Compute totals ──

    total_chars = (
        len(result.legal_context)
        + len(result.personality_context)
        + len(result.wiki_context)
    )
    result.total_tokens_estimate = total_chars // CHARS_PER_TOKEN
    result.retrieval_ms = (time.perf_counter() - start) * 1000

    logger.debug(
        "Unified RAG [%s]: legal=%d wiki=%d personality=%d | %d tokens | %.0fms",
        context_type,
        result.legal_chunks_count,
        result.wiki_pages_count,
        result.personality_entries_count,
        result.total_tokens_estimate,
        result.retrieval_ms,
    )

    return result
