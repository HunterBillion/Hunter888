"""
API routes — AI Continuity Layer of the unified Clients domain.

Prefix: /api/game/clients

Целевая архитектура:
- это не отдельный клиентский модуль
- это continuity/training слой внутри общего домена `Клиенты`
- lifecycle клиента должен оставаться логически совместимым с CRM Core
"""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User
from app.services.game_crm_service import GameCRMService

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic schemas
# ═══════════════════════════════════════════════════════════════════════════════

class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    narrative_date: Optional[str] = None


class ScheduleCallbackRequest(BaseModel):
    scheduled_for: str = Field(..., min_length=1, max_length=200)
    note: Optional[str] = Field(None, max_length=1000)


class ChangeStatusRequest(BaseModel):
    new_status: str = Field(..., min_length=1, max_length=50)
    reason: Optional[str] = Field(None, max_length=500)


class MarkReadRequest(BaseModel):
    event_ids: Optional[list[str]] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/stories")
async def list_stories(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    completed: Optional[bool] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Список игровых историй (клиентов) менеджера.
    Методолог: read-only доступ ко всем.
    """
    service = GameCRMService(db)

    # Для методолога — нужен user_id параметр
    target_user_id = user.id

    return await service.get_stories_list(
        target_user_id,
        limit=limit,
        offset=offset,
        completed=completed,
    )


@router.get("/stories/{story_id}")
async def get_story_detail(
    story_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Детали конкретной игровой истории."""
    service = GameCRMService(db)

    # Access control
    owner_id = _resolve_owner(user, story_id)

    return await service.get_story_detail(story_id, user_id=owner_id)


@router.get("/stories/{story_id}/timeline")
async def get_timeline(
    story_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_types: Optional[str] = Query(None, description="Comma-separated: call,message,consequence,storylet,status_change,callback"),
    include_memories: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Таймлайн игрового клиента — агрегация из всех источников.
    """
    service = GameCRMService(db)

    # Parse event types
    types_list = None
    if event_types:
        types_list = [t.strip() for t in event_types.split(",") if t.strip()]

    return await service.get_client_timeline(
        story_id,
        limit=limit,
        offset=offset,
        event_types=types_list,
        include_memories=include_memories,
    )


@router.post("/stories/{story_id}/message")
async def send_message(
    story_id: uuid.UUID,
    body: SendMessageRequest,
    user: User = Depends(require_role("manager", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Отправить сообщение игровому клиенту (запись в таймлайн)."""
    service = GameCRMService(db)
    owner_id = _resolve_owner(user, story_id)  # None для admin — доступ ко всем
    return await service.send_game_message(
        story_id,
        owner_id,
        user.id,
        content=body.content,
        narrative_date=body.narrative_date,
    )


@router.post("/stories/{story_id}/callback")
async def schedule_callback(
    story_id: uuid.UUID,
    body: ScheduleCallbackRequest,
    user: User = Depends(require_role("manager", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Запланировать обратный звонок игровому клиенту."""
    service = GameCRMService(db)
    owner_id = _resolve_owner(user, story_id)
    return await service.schedule_callback(
        story_id,
        owner_id,
        user.id,
        scheduled_for=body.scheduled_for,
        note=body.note,
    )


@router.patch("/stories/{story_id}/status")
async def change_status(
    story_id: uuid.UUID,
    body: ChangeStatusRequest,
    user: User = Depends(require_role("manager", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Сменить игровой статус клиента."""
    service = GameCRMService(db)
    owner_id = _resolve_owner(user, story_id)
    return await service.change_game_status(
        story_id,
        owner_id,
        user.id,
        new_status=body.new_status,
        reason=body.reason,
    )


@router.post("/stories/{story_id}/read")
async def mark_read(
    story_id: uuid.UUID,
    body: MarkReadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Пометить события таймлайна как прочитанные."""
    service = GameCRMService(db)
    count = await service.mark_events_read(
        story_id,
        user.id,
        event_ids=body.event_ids,
    )
    return {"marked_read": count}


@router.get("/portfolio/stats")
async def portfolio_stats(
    period: str = Query("all", pattern="^(week|month|all)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Статистика портфеля игровых клиентов.
    Redis cache TTL 5 мин.
    """
    service = GameCRMService(db)
    return await service.get_portfolio_stats(user.id, period=period)


@router.get("/portfolio/stats/{manager_id}")
async def portfolio_stats_by_manager(
    manager_id: uuid.UUID,
    period: str = Query("all", pattern="^(week|month|all)$"),
    user: User = Depends(require_role("admin", "rop", "methodologist")),
    db: AsyncSession = Depends(get_db),
):
    """
    Статистика портфеля конкретного менеджера (для РОП/админа/методолога).
    """
    service = GameCRMService(db)
    return await service.get_portfolio_stats(manager_id, period=period)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_owner(user: User, story_id: uuid.UUID) -> uuid.UUID | None:
    """
    Access control: определяем чей user_id использовать для фильтрации.
    - admin/methodologist: None (все), но story_detail проверит по story_id
    - manager: свой user_id
    - rop: TODO — проверка команды
    """
    if user.role.value in ("admin", "methodologist"):
        return None  # get_story_detail will find by story_id
    return user.id
