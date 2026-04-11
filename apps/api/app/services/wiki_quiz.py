"""Wiki → Quiz Integration — generate quiz questions from wiki pages.

Phase 2: "Проверить себя" button on wiki pages generates questions
based on the page content (patterns, techniques, insights).
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manager_wiki import WikiPage

logger = logging.getLogger(__name__)


@dataclass
class WikiQuizQuestion:
    question: str
    expected_answer: str
    difficulty: int
    source_page: str


async def generate_quiz_from_wiki_page(
    page_id: uuid.UUID,
    db: AsyncSession,
    num_questions: int = 5,
    difficulty: int = 3,
) -> list[WikiQuizQuestion]:
    """Generate quiz questions from a wiki page using LLM."""
    from app.services.llm import generate_response

    page = await db.get(WikiPage, page_id)
    if not page or not page.content:
        return []

    result = await generate_response(
        system_prompt=(
            "Ты — экзаменатор по продажам банкротства (127-ФЗ).\n"
            "На основе текста wiki-страницы сгенерируй вопросы для проверки знаний менеджера.\n"
            "Вопросы должны проверять ПОНИМАНИЕ материала, не просто запоминание.\n"
            "Ответь СТРОГО JSON массивом:\n"
            '[{"question": "текст вопроса", "expected_answer": "ожидаемый ответ (2-3 предложения)", "difficulty": 1-5}]\n'
            "Без markdown, без пояснений — только JSON массив."
        ),
        messages=[{
            "role": "user",
            "content": (
                f"Страница: {page.page_path}\n"
                f"Тип: {page.page_type}\n\n"
                f"Содержание:\n{page.content[:2000]}\n\n"
                f"Сгенерируй {num_questions} вопросов сложности ~{difficulty}/5."
            ),
        }],
        task_type="structured",
    )

    if not result or not result.content:
        return []

    # Parse JSON response
    import json
    try:
        # Strip markdown code fences if present
        text = result.content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        questions_raw = json.loads(text)
        if not isinstance(questions_raw, list):
            return []

        return [
            WikiQuizQuestion(
                question=q.get("question", ""),
                expected_answer=q.get("expected_answer", ""),
                difficulty=min(5, max(1, int(q.get("difficulty", difficulty)))),
                source_page=page.page_path,
            )
            for q in questions_raw[:num_questions]
            if q.get("question")
        ]
    except (json.JSONDecodeError, ValueError):
        logger.debug("Failed to parse wiki quiz response for page %s", page.page_path)
        return []
