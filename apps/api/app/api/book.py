"""Book API — structured knowledge library for the home page widget."""
import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/book", tags=["book"])


class BookChapter(BaseModel):
    id: str
    title: str
    icon: str
    description: str
    topics_count: int
    topics: list[dict[str, Any]]


class BookResponse(BaseModel):
    chapters: list[BookChapter]
    total_topics: int


@router.get("", response_model=BookResponse)
async def get_book(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.methodology import MethodologyChunk

    result = await db.execute(
        select(MethodologyChunk).order_by(MethodologyChunk.created_at)
    )
    chunks = result.scalars().all()

    groups: dict[str, list] = {}
    for chunk in chunks:
        kind = chunk.kind or "general"
        groups.setdefault(kind, []).append({
            "id": str(chunk.id),
            "title": chunk.title,
            "body": chunk.body[:300] + "..." if len(chunk.body) > 300 else chunk.body,
            "tags": chunk.tags or [],
            "kind": kind,
        })

    kind_meta = {
        "opener": {"title": "Открытие звонка", "icon": "Phone", "description": "Техники начала разговора и установления контакта"},
        "objection": {"title": "Работа с возражениями", "icon": "Shield", "description": "Ответы на типичные возражения клиентов"},
        "discovery": {"title": "Квалификация", "icon": "Search", "description": "Выявление потребностей и квалификация клиента"},
        "closing": {"title": "Закрытие сделки", "icon": "Trophy", "description": "Техники завершения продажи"},
        "general": {"title": "Общие знания", "icon": "BookOpen", "description": "Основы и справочные материалы"},
    }

    chapters = []
    for kind, topics in groups.items():
        meta = kind_meta.get(kind, {"title": kind.capitalize(), "icon": "FileText", "description": ""})
        chapters.append(BookChapter(
            id=kind,
            title=meta["title"],
            icon=meta["icon"],
            description=meta["description"],
            topics_count=len(topics),
            topics=topics,
        ))

    from app.models.rag import LegalKnowledgeChunk
    legal_count = await db.scalar(select(func.count(LegalKnowledgeChunk.id)))

    if legal_count and legal_count > 0:
        cat_result = await db.execute(
            select(
                LegalKnowledgeChunk.category,
                func.count(LegalKnowledgeChunk.id).label("cnt"),
            )
            .where(LegalKnowledgeChunk.category.isnot(None))
            .group_by(LegalKnowledgeChunk.category)
            .order_by(func.count(LegalKnowledgeChunk.id).desc())
            .limit(20)
        )
        categories = cat_result.all()

        legal_topics = [
            {"id": cat or "other", "title": cat or "Прочее", "count": cnt}
            for cat, cnt in categories
        ]

        chapters.append(BookChapter(
            id="legal",
            title="Законодательство",
            icon="Scale",
            description=f"База знаний по 127-ФЗ и смежным нормам ({legal_count} статей)",
            topics_count=legal_count,
            topics=legal_topics,
        ))

    total = sum(ch.topics_count for ch in chapters)
    return BookResponse(chapters=chapters, total_topics=total)
