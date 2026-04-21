"""Wiki RAG — semantic search over manager's personal wiki pages.

Phase 2: Wiki becomes the THIRD RAG source alongside Legal RAG and Personality RAG.
Enables AI Coach to access manager's patterns, techniques, and insights.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manager_wiki import ManagerWiki, WikiPage
from app.services.llm import get_embedding

logger = logging.getLogger(__name__)


async def retrieve_wiki_context(
    query: str,
    manager_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 3,
    min_similarity: float = 0.20,
) -> list[dict]:
    """Search manager's personal wiki by semantic similarity.

    Returns list of dicts with page_path, content (truncated), similarity score.
    Only pages with embeddings are searchable.
    """
    try:
        query_emb = await get_embedding(query)
    except Exception:
        logger.debug("Failed to get embedding for wiki query, falling back to empty")
        return []

    if not query_emb:
        return []

    # Find manager's wiki
    wiki_result = await db.execute(
        select(ManagerWiki.id).where(ManagerWiki.manager_id == manager_id)
    )
    wiki_id = wiki_result.scalar_one_or_none()
    if not wiki_id:
        return []

    # Cosine similarity search via pgvector
    results = await db.execute(
        select(
            WikiPage.page_path,
            WikiPage.content,
            WikiPage.page_type,
            WikiPage.tags,
            WikiPage.embedding.cosine_distance(query_emb).label("distance"),
        )
        .where(WikiPage.wiki_id == wiki_id)
        .where(WikiPage.embedding.isnot(None))
        .where(WikiPage.page_type != "log")  # Exclude audit logs
        .order_by("distance")
        .limit(top_k)
    )

    wiki_results = []
    for row in results:
        similarity = 1.0 - row.distance  # cosine_distance → similarity
        if similarity < min_similarity:
            continue
        wiki_results.append({
            "page_path": row.page_path,
            "content": row.content[:500] if row.content else "",
            "page_type": row.page_type,
            "tags": row.tags or [],
            "similarity": round(similarity, 3),
        })

    logger.info(
        "Wiki RAG | manager=%s | query='%s' | results=%d",
        manager_id, query[:50], len(wiki_results),
    )
    return wiki_results


async def compound_knowledge(
    manager_id: uuid.UUID,
    query: str,
    synthesis: str,
    source_pages: list[str],
    db: AsyncSession,
) -> bool:
    """Karpathy knowledge compounding: save novel insights back into the wiki.

    When the AI Coach synthesizes an answer from 2+ wiki pages, the synthesis
    itself may contain a novel connection. This function saves it as a new wiki
    page of type 'insight', compounding the wiki's knowledge over time.

    Only saves if:
    - synthesis is substantial (>100 chars)
    - source_pages >= 2 (cross-page insight, not a simple retrieval)
    - No existing insight page with very similar content already exists
    """
    if len(synthesis) < 100 or len(source_pages) < 2:
        return False

    try:
        wiki_result = await db.execute(
            select(ManagerWiki).where(ManagerWiki.manager_id == manager_id)
        )
        wiki = wiki_result.scalar_one_or_none()
        if not wiki:
            return False

        # Check for duplicate: if any existing insight page shares >60% words, skip
        existing_insights = await db.execute(
            select(WikiPage.content)
            .where(WikiPage.wiki_id == wiki.id, WikiPage.page_type == "insight")
            .order_by(WikiPage.updated_at.desc())
            .limit(10)
        )
        synthesis_words = set(synthesis.lower().split())
        for (existing_content,) in existing_insights:
            if existing_content:
                existing_words = set(existing_content.lower().split())
                overlap = len(synthesis_words & existing_words) / max(1, len(synthesis_words))
                if overlap > 0.6:
                    return False  # Too similar to existing insight

        # Generate unique path
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        page_path = f"insights/compound_{now.strftime('%Y%m%d_%H%M%S')}"

        content = (
            f"# Инсайт\n\n"
            f"**Запрос:** {query[:200]}\n\n"
            f"**Источники:** {', '.join(source_pages)}\n\n"
            f"---\n\n"
            f"{synthesis[:2000]}\n"
        )

        page = WikiPage(
            wiki_id=wiki.id,
            page_path=page_path,
            content=content,
            page_type="insight",
            tags=["compound", "auto-generated"] + source_pages[:5],
            source_sessions=[],  # no specific session
        )
        db.add(page)
        await db.flush()

        # Generate embedding for the new insight page
        await generate_wiki_embedding(page, db)

        await db.commit()
        logger.info(
            "Wiki knowledge compounded for manager %s: %s (from %d pages)",
            manager_id, page_path, len(source_pages),
        )
        return True

    except Exception:
        logger.debug("Knowledge compounding failed for manager %s", manager_id, exc_info=True)
        return False


async def generate_wiki_embedding(page: WikiPage, db: AsyncSession) -> bool:
    """Generate and store embedding for a wiki page. Returns True if successful."""
    if not page.content:
        return False

    try:
        # Embed first 1500 chars for deeper semantic coverage (was 500)
        text_to_embed = page.content[:1500]
        embedding = await get_embedding(text_to_embed)
        if embedding:
            page.embedding = embedding
            await db.flush()
            return True
    except Exception:
        logger.debug("Failed to generate embedding for wiki page %s", page.page_path)

    return False
