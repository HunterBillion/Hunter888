"""Best-effort Telegram notifications — non-blocking, graceful degradation.

Usage:
    from app.services.tg_notify import after_session, on_level_up, daily_digest, nudge_inactive
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.user import User
from app.services.telegram_bot import telegram_bot

logger = logging.getLogger(__name__)
PLATFORM = "https://x-hunter.expert"


async def _send_to_user(user_id: str, text: str, reply_markup: dict | None = None) -> bool:
    if not telegram_bot.configured:
        return False
    try:
        async with async_session() as db:
            result = await db.execute(
                select(User).where(User.id == user_id, User.telegram_chat_id.isnot(None))
            )
            user = result.scalar_one_or_none()
            if not user or not user.telegram_chat_id:
                return False
            await telegram_bot.send_message(user.telegram_chat_id, text, reply_markup=reply_markup)
            return True
    except Exception:
        logger.debug("TG notify failed for user %s", user_id, exc_info=True)
        return False


# ── After training session ──────────────────────────────────────────

async def after_session(
    user_id: str,
    user_name: str,
    session_type: str,
    score: float | None,
    weak_points: list[str] | None = None,
    recommendations: list[str] | None = None,
    session_url: str = "",
) -> None:
    """Called from completion_policy after ANY session finalizes."""
    if score is None:
        return

    type_labels = {
        "training": "тренировку",
        "arena": "арену",
        "pvp": "PvP-дуэль",
        "knowledge_quiz": "квиз знаний",
    }
    type_label = type_labels.get(session_type, session_type)

    if score >= 85:
        tone = "\U0001f31f Отличная работа"
    elif score >= 65:
        tone = "\U0001f44d Хороший результат"
    else:
        tone = "\U0001f4aa Ты справился"

    name = user_name.split()[0] if user_name else ""
    lines = [f"<b>{tone}, {name}!</b>"]
    lines.append(f"Ты завершил {type_label} с результатом <b>{score:.0f}%</b>.")

    if weak_points:
        lines.append("")
        lines.append("Над чем стоит поработать:")
        for wp in weak_points[:3]:
            lines.append(f"  \u2022 {wp}")
    if recommendations:
        lines.append("")
        for rec in recommendations[:2]:
            lines.append(f"{rec}")

    if session_url:
        lines.append("")
        lines.append(f'<a href="{session_url}">Подробный разбор \u2192</a>')

    await _send_to_user(user_id, "\n".join(lines))


# ── Level up ────────────────────────────────────────────────────────

async def on_level_up(user_id: str, new_level: int, level_name: str) -> None:
    await _send_to_user(
        user_id,
        f"\U0001f389 <b>Новый уровень!</b>\n\n"
        f"Ты дошёл до <b>{new_level} уровня</b> \u2014 {level_name}.\n\n"
        f"Это результат твоей работы. Так держать!",
    )


# ── Exam passed ─────────────────────────────────────────────────────

async def on_exam_passed(user_id: str, user_name: str, level: int, score: float, serial: str = "") -> None:
    name = user_name.split()[0] if user_name else ""
    serial_line = f"\nСертификат: <code>{serial}</code>" if serial else ""
    await _send_to_user(
        user_id,
        f"\U0001f3c6 <b>{name}, экзамен сдан!</b>\n\n"
        f"Результат: <b>{score:.0f}%</b>\n"
        f"Уровень {level} разблокирован.{serial_line}\n\n"
        f"Это серьёзное достижение.",
    )


async def on_exam_failed(user_id: str, user_name: str, score: float, required: float, level: int | None = None) -> None:
    name = user_name.split()[0] if user_name else ""
    level_text = f" для уровня {level}" if level else ""
    await _send_to_user(
        user_id,
        f"\U0001f4da <b>{name}, пока не получилось{level_text}</b>\n\n"
        f"Набрано {score:.0f}%, нужно {required:.0f}%.\n\n"
        f"Ничего страшного \u2014 подготовься и попробуй снова. "
        f"Вторая попытка всегда лучше.",
    )


# ── Daily digest at 09:00 ───────────────────────────────────────────

async def daily_digest() -> int:
    """Send morning summary to all linked TG users with activity yesterday."""
    import asyncio
    now = datetime.now(timezone.utc)
    today = now.date()
    yesterday = today - timedelta(days=1)

    async with async_session() as db:
        from app.models.training import TrainingSession
        from app.models.progress import ManagerProgress

        # Find linked users who trained yesterday
        result = await db.execute(
            select(User.id, User.full_name, User.telegram_chat_id)
            .where(
                User.telegram_chat_id.isnot(None),
                User.is_active.is_(True),
                User.id.in_(
                    select(TrainingSession.user_id).where(
                        func.date(TrainingSession.started_at) == yesterday,
                        TrainingSession.status == "completed",
                    )
                ),
            )
        )
        users = result.all()
        sent = 0

        for (uid, name, chat_id) in users:
            try:
                # Get progress
                prog_result = await db.execute(
                    select(ManagerProgress).where(ManagerProgress.user_id == uid)
                )
                progress = prog_result.scalar_one_or_none()

                # Count yesterday's sessions
                count_result = await db.execute(
                    select(func.count()).where(
                        TrainingSession.user_id == uid,
                        func.date(TrainingSession.started_at) == yesterday,
                        TrainingSession.status == "completed",
                    )
                )
                session_count = count_result.scalar() or 0

                first = name.split()[0] if name else ""
                if progress:
                    lines = [
                        f"\U0001f305 <b>Доброе утро, {first}!</b>\n",
                        f"Вчера: <b>{session_count}</b> сессий.",
                        f"Уровень: <b>{progress.current_level}</b>. XP: <b>{progress.total_xp}</b>.",
                    ]
                else:
                    lines = [
                        f"\U0001f305 <b>Доброе утро, {first}!</b>\n",
                        f"Вчера: <b>{session_count}</b> сессий.",
                    ]

                lines.append("")
                lines.append(f'<a href="{PLATFORM}/training">Продолжить тренировки \u2192</a>')

                await telegram_bot.send_message(chat_id, "\n".join(lines))
                sent += 1
                await asyncio.sleep(0.05)  # rate-limit
            except Exception:
                logger.debug("Daily digest failed for user %s", uid, exc_info=True)

    logger.info("Daily digest sent to %d users", sent)
    return sent


# ── Inactive nudge: no sessions in 3+ days ──────────────────────────

async def nudge_inactive() -> int:
    """Remind users who haven't trained in 3+ days."""
    import asyncio
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=3)

    async with async_session() as db:
        from app.models.training import TrainingSession

        result = await db.execute(
            select(User.id, User.full_name, User.telegram_chat_id)
            .where(
                User.telegram_chat_id.isnot(None),
                User.is_active.is_(True),
                ~User.id.in_(
                    select(TrainingSession.user_id).where(
                        TrainingSession.started_at > threshold,
                        TrainingSession.status == "completed",
                    )
                ),
            )
            .limit(100)
        )
        users = result.all()
        sent = 0

        for (uid, name, chat_id) in users:
            try:
                first = name.split()[0] if name else ""
                await telegram_bot.send_message(
                    chat_id,
                    f"\U0001f4ec <b>{first}, привет!</b>\n\n"
                    f"Ты не тренировался уже несколько дней. Навыки, как мышцы \u2014 "
                    f"работают лучше с регулярной практикой.\n\n"
                    f"Даже одна короткая сессия сегодня \u2014 уже шаг вперёд.\n\n"
                    f'<a href="{PLATFORM}/training">Начать тренировку \u2192</a>',
                )
                sent += 1
                await asyncio.sleep(0.05)
            except Exception:
                logger.debug("Nudge failed for user %s", uid, exc_info=True)

    logger.info("Inactive nudge sent to %d users", sent)
    return sent
