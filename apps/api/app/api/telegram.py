"""Telegram Bot webhook & account linking API."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.telegram_bot import telegram_bot, generate_link_code, consume_link_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/telegram", tags=["telegram"])


class LinkCodeResponse(BaseModel):
    code: str
    bot_username: str
    expires_seconds: int = 300


class TelegramStatusResponse(BaseModel):
    linked: bool
    chat_id: int | None = None


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    try:
        body = await request.json()
    except Exception:
        return {"ok": True}

    message = body.get("message")
    if not message:
        return {"ok": True}

    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    tg_user = message.get("from", {})
    tg_name = tg_user.get("first_name", "")

    if not chat_id or not text:
        return {"ok": True}

    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and len(parts[1]) == 6:
            code = parts[1]
            user_id = consume_link_code(code)
            if user_id:
                await db.execute(
                    update(User).where(User.id == user_id).values(telegram_chat_id=chat_id)
                )
                await db.commit()
                await telegram_bot.send_message(
                    chat_id,
                    f"✅ <b>Привет, {tg_name}!</b>\n\n"
                    f"Telegram привязан к Hunter888.\n"
                    f"Буду присылать разбор после каждой сессии.\n\n"
                    f"/status — прогресс\n/help — команды",
                )
            else:
                await telegram_bot.send_message(chat_id, "❌ Код устарел или неверный.")
        else:
            await telegram_bot.send_message(
                chat_id,
                f"👋 <b>Привет, {tg_name}!</b>\n\n"
                f"Я бот Hunter888.\nПривяжи аккаунт в настройках платформы.\n/help — команды",
            )
        return {"ok": True}

    if text == "/status":
        result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
        user = result.scalar_one_or_none()
        if not user:
            await telegram_bot.send_message(chat_id, "❌ Аккаунт не привязан.")
            return {"ok": True}
        from app.models.progress import ManagerProgress
        prog_result = await db.execute(
            select(ManagerProgress).where(ManagerProgress.user_id == user.id)
        )
        progress = prog_result.scalar_one_or_none()
        if progress:
            from scripts.seed_levels import get_level_name
            level_name = get_level_name(progress.current_level)
            await telegram_bot.send_message(
                chat_id,
                f"📊 <b>Твой прогресс:</b>\n\n"
                f"Уровень: <b>{progress.current_level}</b> — {level_name}\n"
                f"XP: <b>{progress.current_xp}</b>\n"
                f"Сессий: <b>{progress.total_sessions}</b>",
            )
        else:
            await telegram_bot.send_message(chat_id, "📊 Прогресс пуст. Проведи первую тренировку!")
        return {"ok": True}

    if text == "/unlink":
        result = await db.execute(select(User).where(User.telegram_chat_id == chat_id))
        user = result.scalar_one_or_none()
        if user:
            await db.execute(update(User).where(User.id == user.id).values(telegram_chat_id=None))
            await db.commit()
            await telegram_bot.send_message(chat_id, "🔓 Аккаунт отвязан.")
        else:
            await telegram_bot.send_message(chat_id, "Аккаунт не был привязан.")
        return {"ok": True}

    if text == "/help":
        await telegram_bot.send_message(
            chat_id,
            "🤖 <b>Команды:</b>\n\n/status — прогресс\n/unlink — отвязать\n/help — справка\n\n"
            "Автоматически присылаю разбор ошибок после сессий.",
        )
        return {"ok": True}

    if text.startswith("/"):
        await telegram_bot.send_message(chat_id, "Не знаю такой команды. /help")
        return {"ok": True}

    return {"ok": True}


@router.post("/link", response_model=LinkCodeResponse)
async def create_link_code(user: User = Depends(get_current_user)):
    if not telegram_bot.configured:
        raise HTTPException(status_code=503, detail="Telegram бот не настроен")
    code = generate_link_code(str(user.id))
    return LinkCodeResponse(code=code, bot_username=settings.telegram_bot_username)


@router.delete("/link", status_code=204)
async def unlink_telegram(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    await db.execute(update(User).where(User.id == user.id).values(telegram_chat_id=None))
    await db.commit()


@router.get("/status", response_model=TelegramStatusResponse)
async def telegram_status(user: User = Depends(get_current_user)):
    return TelegramStatusResponse(
        linked=user.telegram_chat_id is not None,
        chat_id=user.telegram_chat_id,
    )
