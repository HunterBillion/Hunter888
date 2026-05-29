"""Post-session feedback generator for Telegram.

Uses Navy API to analyze session errors and generate bro-mentor feedback.
Triggered by event_bus after session completion (10s delay).
"""
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


async def generate_and_send_feedback(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    session_type: str,
    db: AsyncSession,
) -> None:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.telegram_chat_id:
        return

    from app.models.training import TrainingSession
    sess_result = await db.execute(
        select(TrainingSession).where(TrainingSession.id == session_id)
    )
    session = sess_result.scalar_one_or_none()
    if not session or session.status != "completed":
        return

    score = session.score_total
    scoring = session.scoring_details or {}
    weak_points = _extract_weak_points(scoring, session_type)
    recommendations = await _generate_recommendations(
        user_name=user.full_name or "менеджер",
        session_type=session_type,
        score=score,
        weak_points=weak_points,
    )

    from app.services.telegram_bot import telegram_bot
    session_url = f"{settings.frontend_url}/results/{session_id}"
    await telegram_bot.send_session_feedback(
        chat_id=user.telegram_chat_id,
        user_name=user.full_name or "бро",
        session_type=session_type,
        score=score,
        weak_points=weak_points,
        recommendations=recommendations,
        session_url=session_url,
    )
    logger.info("TG feedback sent: user=%s session=%s", user_id, session_id)


def _extract_weak_points(scoring: dict, session_type: str) -> list[str]:
    weak = []
    if session_type in ("training", "arena"):
        for key, label in [
            ("communication", "Коммуникация"),
            ("legal_accuracy", "Юридическая точность"),
            ("objection_handling", "Работа с возражениями"),
            ("empathy_rapport", "Эмпатия"),
            ("scenario_completion", "Завершение сценария"),
        ]:
            val = scoring.get(f"score_{key}") or scoring.get(key)
            if val is not None and isinstance(val, (int, float)) and val < 3.0:
                weak.append(f"{label}: {val:.1f}/5")

        traps = scoring.get("trap_handling", {}).get("traps", [])
        for trap in traps:
            if trap.get("result") in ("failed", "partial"):
                trap_name = trap.get("trap_type", trap.get("name", "ловушка"))
                weak.append(f"Ловушка «{trap_name}» — не пройдена")

        legal_weak = scoring.get("weak_legal_categories", [])
        for cat in legal_weak[:3]:
            weak.append(f"Слабая тема: {cat}")

    elif session_type == "knowledge_quiz":
        wrong = scoring.get("wrong_count", 0)
        total = scoring.get("total_questions", 0)
        if wrong > 0:
            weak.append(f"Ошибок: {wrong} из {total}")
        for topic in scoring.get("weak_topics", [])[:3]:
            weak.append(f"Тема: {topic}")

    return weak[:7]


async def _generate_recommendations(
    user_name: str, session_type: str, score: float | None, weak_points: list[str],
) -> list[str]:
    if not weak_points:
        return ["Отличная работа! Продолжай в том же духе."]

    if not settings.local_llm_enabled:
        return _fallback_recommendations(weak_points)

    try:
        import httpx
        prompt = (
            f"Ты наставник менеджера по взысканию. "
            f"Тренировка типа «{session_type}», результат: {score or 'нет'}%. "
            f"Слабые места: {'; '.join(weak_points)}. "
            f"Дай 1-2 коротких совета (каждый до 50 слов) как улучшить эти аспекты. "
            f"Стиль: дружеский, обращение на «ты»."
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.local_llm_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.local_llm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.local_llm_model,
                    "messages": [
                        {"role": "system", "content": "Ты краткий наставник. Отвечай списком из 1-2 советов."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.7,
                },
            )
            data = resp.json()
            text = data["choices"][0]["message"]["content"].strip()
            lines = [
                line.strip().lstrip("0123456789.-) ").strip()
                for line in text.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
            return lines[:3] if lines else [text[:200]]
    except Exception as exc:
        logger.warning("Navy API recommendation failed: %s", exc)
        return _fallback_recommendations(weak_points)


def _fallback_recommendations(weak_points: list[str]) -> list[str]:
    recs = []
    for wp in weak_points[:2]:
        wp_lower = wp.lower()
        if "коммуникация" in wp_lower or "эмпатия" in wp_lower:
            recs.append("Попробуй активнее слушать и использовать имя клиента.")
        elif "юрид" in wp_lower or "закон" in wp_lower or "тема:" in wp_lower:
            recs.append("Повтори эту тему в книге или пройди квиз.")
        elif "ловушка" in wp_lower:
            recs.append("Не торопись с ответом на провокации — бери паузу.")
        elif "возражен" in wp_lower:
            recs.append("Потренируй отработку возражений в режиме арены.")
        else:
            recs.append("Пройди тренировку ещё раз — с каждым разом становится лучше.")
    return recs if recs else ["Повтори слабые темы и попробуй ещё раз!"]
