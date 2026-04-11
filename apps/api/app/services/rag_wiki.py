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


async def generate_wiki_embedding(page: WikiPage, db: AsyncSession) -> bool:
    """Generate and store embedding for a wiki page. Returns True if successful."""
    if not page.content:
        return False

    try:
        # Embed first 500 chars (content summary)
        text_to_embed = page.content[:500]
        embedding = await get_embedding(text_to_embed)
        if embedding:
            page.embedding = embedding
            await db.flush()
            return True
    except Exception:
        logger.debug("Failed to generate embedding for wiki page %s", page.page_path)

    return False
