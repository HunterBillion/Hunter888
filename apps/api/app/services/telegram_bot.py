"""Telegram Bot API client — stateless, httpx-based.

Singleton: `telegram_bot = TelegramBot()`
Link codes: in-memory dict with 5-min TTL.
"""
import logging
import random
import string
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# ── Link codes (in-memory, 5-min TTL) ────────────────────────────────

_link_codes: dict[str, tuple[str, float]] = {}  # code -> (user_id, expires_at)


def generate_link_code(user_id: str) -> str:
    """Generate a 6-digit code for Telegram account linking."""
    code = "".join(random.choices(string.digits, k=6))
    _link_codes[code] = (user_id, time.time() + 300)
    return code


def consume_link_code(code: str) -> str | None:
    """Consume a link code, returning user_id if valid."""
    entry = _link_codes.pop(code, None)
    if not entry:
        return None
    user_id, expires_at = entry
    if time.time() > expires_at:
        return None
    return user_id


# ── Bot client ────────────────────────────────────────────────────────

class TelegramBot:
    """Stateless Telegram Bot API client."""

    def __init__(self) -> None:
        self.token = settings.telegram_bot_token
        self.configured = bool(self.token)
        if self.configured:
            self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def send_message(
        self, chat_id: int, text: str, parse_mode: str = "HTML"
    ) -> dict[str, Any] | None:
        if not self.configured:
            return None
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                )
                return resp.json()
        except Exception as e:
            logger.warning("TG sendMessage failed: %s", e)
            return None

    async def send_session_feedback(
        self,
        chat_id: int,
        user_name: str,
        session_type: str,
        score: float | None,
        weak_points: list[str],
        recommendations: list[str],
        session_url: str,
    ) -> None:
        type_labels = {
            "training": "Тренировка",
            "arena": "Арена",
            "pvp": "PvP",
            "knowledge_quiz": "Квиз",
        }
        type_label = type_labels.get(session_type, session_type)
        score_str = f"{score:.0f}%" if score else "—"

        lines = [
            f"📊 <b>{type_label} завершена!</b>",
            f"",
            f"Привет, {user_name}! Вот твой разбор:",
            f"Результат: <b>{score_str}</b>",
        ]

        if weak_points:
            lines.append("")
            lines.append("⚠️ <b>Слабые места:</b>")
            for wp in weak_points[:5]:
                lines.append(f"  • {wp}")

        if recommendations:
            lines.append("")
            lines.append("💡 <b>Советы:</b>")
            for rec in recommendations[:3]:
                lines.append(f"  → {rec}")

        lines.append("")
        lines.append(f'<a href="{session_url}">Подробный разбор →</a>')

        await self.send_message(chat_id, "\n".join(lines))

    async def send_level_up(
        self, chat_id: int, user_name: str, new_level: int, level_name: str
    ) -> None:
        await self.send_message(
            chat_id,
            f"🎉 <b>Поздравляю, {user_name}!</b>\n\n"
            f"Ты достиг уровня <b>{new_level}</b> — {level_name}!\n"
            f"Новые возможности разблокированы. Продолжай в том же духе! 💪",
        )

    async def send_exam_required(
        self, chat_id: int, user_name: str, level: int
    ) -> None:
        await self.send_message(
            chat_id,
            f"📝 <b>{user_name}, пора сдать экзамен!</b>\n\n"
            f"Для перехода на уровень {level} нужно пройти экзамен.\n"
            f"Зайди в раздел Тренировки → Экзамены.",
        )

    async def send_exam_passed(
        self,
        chat_id: int,
        user_name: str,
        level: int,
        level_name: str,
        score: float,
        serial: str,
    ) -> None:
        await self.send_message(
            chat_id,
            f"🏆 <b>Экзамен сдан, {user_name}!</b>\n\n"
            f"Уровень {level} — {level_name}\n"
            f"Результат: <b>{score:.1f}%</b>\n"
            f"Сертификат: <code>{serial}</code>\n\n"
            f"Поздравляю! 🎉",
        )

    async def send_exam_failed(
        self,
        chat_id: int,
        user_name: str,
        level: int,
        score: float,
        threshold: float,
    ) -> None:
        await self.send_message(
            chat_id,
            f"📝 <b>{user_name}, экзамен не сдан</b>\n\n"
            f"Результат: {score:.1f}% (нужно {threshold:.0f}%)\n"
            f"Не расстраивайся — повтори слабые темы и попробуй снова! 💪",
        )

    async def set_webhook(self, webhook_url: str) -> dict | None:
        if not self.configured:
            return None
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/setWebhook",
                    json={
                        "url": webhook_url,
                        "secret_token": settings.telegram_webhook_secret,
                    },
                )
                return resp.json()
        except Exception as e:
            logger.warning("TG setWebhook failed: %s", e)
            return None


telegram_bot = TelegramBot()
