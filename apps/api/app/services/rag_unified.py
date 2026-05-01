"""
Unified RAG — single entry point for all 3 RAG sources (Task 2.4).

Calls Legal, Personality, and Wiki RAG in parallel.
Merges results with context-dependent token budgets.
Respects 8K model constraint: total RAG budget = 1500 tokens.

Post-2026-04-17 upgrade — when env RAG_LEGAL_USE_V2=true:
  - Legal retrieval goes through `rag_legal_v2.retrieve_legal_context_v2`
    which queries BOTH legal_knowledge_chunks AND legal_document via
    gemini-embedding-001@768 + optional LLM reranker + confidence gate.
  - Otherwise falls back to legacy `rag_legal.retrieve_legal_context`
    (text-embedding-3-small → legal_knowledge_chunks.embedding only).
  - The flag is OFF by default so nothing breaks until embedding_v2 is
    100% populated on both tables.

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
import os
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _use_legal_v2() -> bool:
    """Env feature flag for the new dual-table legal RAG path."""
    return os.environ.get("RAG_LEGAL_USE_V2", "").lower() in {"1", "true", "yes", "on"}

# ─── Token budgets per context type ─────────────────────────────────────────
# Total: ~1700 tokens for training (safe for 8K Gemma context with ~4K system prompt)
# CHARS_PER_TOKEN ≈ 2 for Russian text

BUDGET = {
    "training": {"legal": 700, "personality": 400, "wiki": 250, "methodology": 350},
    "coach":    {"legal": 500, "personality": 250, "wiki": 350, "methodology": 600},
    "quiz":     {"legal": 1000, "personality": 0, "wiki": 200, "methodology": 0},
}
# Coach gets the largest methodology bucket — that's the headline
# value of TZ-8 ("show me how WE do it"). Quiz=0 because the
# knowledge quiz tests recall of objective facts, not procedure.
# Total per context ≤ 1700 tokens (8K-context safe; see TZ-8 §3.6).
# Training personality reduced from 500 → 400 to fit the methodology
# bucket within the 1700 cap; the lorebook assembly in llm.py:2062
# is the primary consumer of personality and runs on its own budget.

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
    methodology_context: str = ""
    legal_chunks_count: int = 0
    personality_entries_count: int = 0
    wiki_pages_count: int = 0
    methodology_chunks_count: int = 0
    wiki_pages: list[dict] = field(default_factory=list)  # raw wiki results for knowledge compounding
    methodology_chunks: list[dict] = field(default_factory=list)  # raw methodology results for telemetry / UI debug
    total_tokens_estimate: int = 0
    retrieval_ms: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def has_legal(self) -> bool:
        return bool(self.legal_context)

    @property
    def has_wiki(self) -> bool:
        return bool(self.wiki_context)

    @property
    def has_methodology(self) -> bool:
        return bool(self.methodology_context)

    def to_prompt(self) -> str:
        """Format all RAG context for system prompt injection.

        PR-X foundation fix #2 — both blocks (legal & wiki) are wrapped
        in ``[DATA_START] ... [DATA_END]`` isolation markers so the LLM
        treats them as data, not instructions. The system prompt that
        consumes this output (see ``test_rag_security.py::TestDataMarkers``)
        already understands these markers because the legal path has used
        them since S1-01. Wiki used to be raw concatenation — a ROP who
        pasted ``Ignore all previous instructions…`` into a page edit
        would jailbreak every coach session that surfaced the page.
        ``filter_wiki_context`` (called upstream of the merger) plus the
        markers here close that gap.

        AST-invariant ``test_wiki_invariants.py`` enforces that
        ``UnifiedRAGResult.wiki_context`` is read **only** inside this
        function (and inside the dataclass definition itself). Any new
        consumer that needs wiki content must call ``to_prompt()`` and
        receive the wrapped form — never the raw string.
        """
        parts: list[str] = []

        if self.legal_context:
            parts.append(
                "ПРАВОВАЯ БАЗА (127-ФЗ):\n" + self.legal_context
            )

        if self.methodology_context:
            # Team methodology block — same isolation contract as
            # wiki/legal. Placed BEFORE wiki so the prompt order
            # mirrors the budget order (methodology > wiki for
            # coach/training; wiki > methodology for nothing).
            # AST-invariant in test_rag_invariants.py enforces that
            # methodology_context is read only inside this method.
            parts.append(
                "МЕТОДОЛОГИЯ КОМАНДЫ:\n"
                "[DATA_START]\n"
                + self.methodology_context
                + "\n[DATA_END]"
            )

        if self.wiki_context:
            # The marker pair MUST stay in lock-step with the legal
            # path's ``RAGContext.to_prompt_context`` and with the
            # AST-invariant in ``test_rag_invariants.py``. Renaming
            # them is a TZ §13 review.
            parts.append(
                "ПЕРСОНАЛЬНАЯ WIKI МЕНЕДЖЕРА:\n"
                "[DATA_START]\n"
                + self.wiki_context
                + "\n[DATA_END]"
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
    team_id: UUID | None = None,
) -> UnifiedRAGResult:
    """
    Retrieve context from all 4 RAG sources in parallel.

    Args:
        query: Search query (user message or scenario description)
        user_id: Manager's user ID (for Wiki RAG personalization)
        db: Database session
        context_type: "training" | "coach" | "quiz" — determines token weights
        archetype_code: For Personality RAG (optional, only for training)
        emotion_state: For Personality RAG (optional)
        team_id: Manager's team UUID (for Methodology RAG). When
            ``None``, methodology RAG is skipped — it has no
            "global" notion (TZ-8 §1) so a missing team_id means
            no scope is available. Pass ``user.team_id`` from
            the caller.

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
            top_k = 3 if budgets["legal"] <= 600 else 5
            async with _make_session() as rag_db:
                if _use_legal_v2():
                    # Dual-table path: legal_knowledge_chunks + legal_document
                    # via gemini-embedding-001@768 with reranker + confidence gate.
                    from app.services.rag_legal_v2 import (
                        retrieve_legal_context_v2, RetrieveV2Options,
                    )
                    opts = RetrieveV2Options(
                        top_k=top_k,
                        candidate_pool=max(20, top_k * 4),
                        use_reranker=True,
                        confidence_threshold=0.55,
                    )
                    return await retrieve_legal_context_v2(query, rag_db, opts)
                else:
                    # Legacy single-table path — until embedding_v2 backfill
                    # is 100% complete, this is the source of truth.
                    from app.services.rag_legal import (
                        retrieve_legal_context, RetrievalConfig,
                    )
                    config = RetrievalConfig(top_k=top_k, mode="free_dialog")
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

    # Methodology RAG (TZ-8 PR-B). Per-team — needs ``team_id`` from
    # the caller. Quiz path has budget=0 so no scan; training/coach
    # paths skip the task when team_id is unknown rather than risk
    # cross-team leakage from a fallback.
    if budgets.get("methodology", 0) > 0 and team_id is not None:

        async def _methodology():
            from app.database import async_session as _make_session
            from app.services.rag_methodology import (
                retrieve_methodology_context,
            )

            async with _make_session() as rag_db:
                # Pass ``user_id`` so the retriever can log usage
                # (TZ-8 PR-D telemetry). ``source_type`` matches the
                # context_type so the effectiveness panel can split
                # "fired in coach" vs "fired in training".
                return await retrieve_methodology_context(
                    query,
                    team_id,
                    rag_db,
                    top_k=4,
                    user_id=user_id,
                    source_type=context_type,
                )

        tasks["methodology"] = asyncio.create_task(_methodology())

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
                    # PR-X foundation fix #2 — sanitise user-edited
                    # markdown for prompt injection / PII / length
                    # before it ever lands in the system prompt. Mutates
                    # ``raw`` in place; downstream knowledge-compounding
                    # gets the cleaned version too (intentional — we
                    # don't want injected content surviving anywhere).
                    from app.services.content_filter import filter_wiki_context

                    raw, _wiki_violations = filter_wiki_context(raw)
                    lines = [
                        f"- [{r['page_path']}]: {r['content'][:200]}"
                        for r in raw
                        if r.get("content")
                    ]
                    if lines:
                        text = "\n".join(lines)
                        result.wiki_context = _trim(text, budgets["wiki"])
                        result.wiki_pages_count = len(lines)
                        result.wiki_pages = raw  # preserve for knowledge compounding

            elif name == "methodology":
                if raw:  # list[dict] from rag_methodology
                    # TZ-8 PR-B — same write-side hygiene as wiki:
                    # ``filter_methodology_context`` runs before the
                    # block hits the prompt builder. AST-invariant in
                    # ``test_rag_invariants.py`` confirms the
                    # methodology_context attribute is read only
                    # inside ``UnifiedRAGResult.to_prompt`` so a
                    # future consumer can't sneak around the filter.
                    from app.services.content_filter import (
                        filter_methodology_context,
                    )

                    raw, _meth_violations = filter_methodology_context(raw)
                    lines = []
                    for c in raw:
                        body = c.get("body") or ""
                        if not body:
                            continue
                        # Title precedes the body so the LLM sees
                        # "Closing playbook: …" rather than an
                        # untitled bullet. Truncate body to 300
                        # chars for the prompt block — the full
                        # text stays in result.methodology_chunks
                        # for telemetry / UI.
                        lines.append(
                            f"- [{c.get('kind', 'other')}] "
                            f"{c.get('title', '?')}: {body[:300]}"
                        )
                    if lines:
                        text = "\n".join(lines)
                        result.methodology_context = _trim(
                            text, budgets["methodology"]
                        )
                        result.methodology_chunks_count = len(lines)
                        result.methodology_chunks = raw

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
        + len(result.methodology_context)
    )
    result.total_tokens_estimate = total_chars // CHARS_PER_TOKEN
    result.retrieval_ms = (time.perf_counter() - start) * 1000

    logger.debug(
        "Unified RAG [%s]: legal=%d methodology=%d wiki=%d personality=%d | %d tokens | %.0fms",
        context_type,
        result.legal_chunks_count,
        result.methodology_chunks_count,
        result.wiki_pages_count,
        result.personality_entries_count,
        result.total_tokens_estimate,
        result.retrieval_ms,
    )

    return result
