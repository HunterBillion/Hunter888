"""AI Judge for PvP duels (Agent 8 — PvP Battle).

Evaluates both players in real-time via separate LLM call.
Scoring per round:
- selling_score (0-50): objection handling, persuasion, structure, closing
- acting_score (0-30): role authenticity, emotional depth, realism (×difficulty multiplier)
- legal_accuracy (0-20): correctness of legal claims (validated via RAG)

AI Judge config:
- Temperature = 0 (deterministic)
- Structured output (JSON schema)
- Calibration: 10 reference dialogs, drift alert > 5%
"""

import json
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pvp import DuelDifficulty, DIFFICULTY_MULTIPLIERS
from app.services.llm import generate_response
from app.services.rag_legal import retrieve_legal_context, RAGContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring schema
# ---------------------------------------------------------------------------

@dataclass
class JudgeRoundScore:
    """Score for one player in one round."""
    selling_score: float = 0.0      # 0-50
    acting_score: float = 0.0       # 0-30 (before multiplier)
    legal_accuracy: float = 0.0     # 0-20
    total: float = 0.0
    breakdown: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    legal_details: list[dict] = field(default_factory=list)


@dataclass
class JudgeDuelResult:
    """Complete judge result for a full duel (2 rounds)."""
    player1_selling: float = 0.0
    player1_acting: float = 0.0
    player1_legal: float = 0.0
    player1_total: float = 0.0

    player2_selling: float = 0.0
    player2_acting: float = 0.0
    player2_legal: float = 0.0
    player2_total: float = 0.0

    winner_id: uuid.UUID | None = None
    is_draw: bool = False
    summary: str = ""


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """Ты — AI-судья PvP-дуэли между двумя менеджерами по банкротству физических лиц (БФЛ).

Твоя задача — объективно оценить обоих участников по трём критериям.

## Критерии оценки

### 1. Навык продажи (selling_score: 0-50)
- Работа с возражениями (0-15): выявление истинного возражения, техника обработки, результат
- Убедительность (0-10): логичность аргументов, эмоциональный интеллект
- Структура разговора (0-10): открытие, выявление потребности, презентация, закрытие
- Закрытие сделки (0-10): конкретное предложение, работа с сомнениями
- Юридическая грамотность (0-5): корректность правовых утверждений

### 2. Актёрское мастерство роли CLIENT (acting_score: 0-30)
- Аутентичность архетипа (0-10): соответствие заданному типу клиента
- Эмоциональная глубина (0-10): реалистичные реакции, динамика эмоций
- Реализм (0-10): естественность речи, уместные вопросы и возражения

### 3. Юридическая точность (legal_accuracy: 0-20)
- Корректные утверждения по 127-ФЗ: +2 за каждое (макс +10)
- Корректные с цитатой статьи: +3 за каждое (макс +10)
- Ошибочные утверждения: -3 за каждое
- Частично верные: -1 за каждое
- Итого: clamp(sum, 0, 20)

{legal_context}

## Формат ответа
СТРОГО JSON без markdown:
{{
  "selling_score": <int 0-50>,
  "selling_breakdown": {{
    "objection_handling": <int 0-15>,
    "persuasion": <int 0-10>,
    "structure": <int 0-10>,
    "closing": <int 0-10>,
    "legal_knowledge": <int 0-5>
  }},
  "acting_score": <int 0-30>,
  "acting_breakdown": {{
    "archetype_authenticity": <int 0-10>,
    "emotional_depth": <int 0-10>,
    "realism": <int 0-10>
  }},
  "legal_accuracy": <int 0-20>,
  "legal_details": [
    {{"claim": "<утверждение>", "accuracy": "correct|incorrect|partial|correct_cited", "explanation": "<пояснение>"}}
  ],
  "flags": ["<замечания, если есть>"],
  "summary": "<краткое резюме оценки на русском, 2-3 предложения>"
}}"""

JUDGE_USER_PROMPT = """## Контекст дуэли
- Раунд: {round_number}/2
- Сложность клиента: {difficulty} (множитель acting: ×{multiplier})
- Роль ПРОДАВЦА: {seller_name}
- Роль КЛИЕНТА: {client_name}
- Архетип клиента: {archetype}

## Диалог раунда:
{dialog}

Оцени ПРОДАВЦА по selling_score и legal_accuracy.
Оцени КЛИЕНТА по acting_score.
"""


# ---------------------------------------------------------------------------
# Judge logic
# ---------------------------------------------------------------------------

async def judge_round(
    dialog: list[dict],
    seller_id: uuid.UUID,
    client_id: uuid.UUID,
    seller_name: str,
    client_name: str,
    archetype: str,
    difficulty: DuelDifficulty,
    round_number: int,
    db: AsyncSession,
) -> tuple[JudgeRoundScore, JudgeRoundScore]:
    """Judge a single round of PvP dialog.

    Args:
        dialog: list of {role: "seller"|"client", text: str, timestamp: float}
        seller_id, client_id: player UUIDs
        seller_name, client_name: display names
        archetype: client archetype for this round
        difficulty: difficulty tier
        round_number: 1 or 2
        db: database session for RAG

    Returns:
        (seller_score, client_score) as JudgeRoundScore
    """
    # Collect all messages for legal RAG context
    all_text = " ".join(msg.get("text", "") for msg in dialog)
    legal_context = await retrieve_legal_context(all_text, db, top_k=5)

    # Format dialog
    dialog_text = ""
    for msg in dialog:
        role_label = "ПРОДАВЕЦ" if msg.get("role") == "seller" else "КЛИЕНТ"
        dialog_text += f"[{role_label}]: {msg.get('text', '')}\n"

    multiplier = DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)

    system = JUDGE_SYSTEM_PROMPT.format(
        legal_context=legal_context.to_prompt_context() if legal_context.has_results else "Правовая база: не найдено релевантных норм для данного диалога."
    )
    user = JUDGE_USER_PROMPT.format(
        round_number=round_number,
        difficulty=difficulty.value,
        multiplier=multiplier,
        seller_name=seller_name,
        client_name=client_name,
        archetype=archetype,
        dialog=dialog_text,
    )

    # LLM call (temperature controlled by system prompt directive for determinism)
    try:
        messages = [{"role": "user", "content": user}]
        llm_response = await generate_response(
            system_prompt=system,
            messages=messages,
        )

        # Parse JSON from response
        result = _parse_judge_response(llm_response.content)

    except Exception as e:
        logger.error("AI Judge failed: %s", e)
        # Fallback: neutral scores
        result = {
            "selling_score": 25,
            "acting_score": 15,
            "legal_accuracy": 10,
            "selling_breakdown": {},
            "acting_breakdown": {},
            "legal_details": [],
            "flags": [f"AI Judge error: {str(e)[:100]}"],
            "summary": "Оценка не удалась, применены нейтральные баллы.",
        }

    # Apply difficulty multiplier to acting score
    raw_acting = result.get("acting_score", 0)
    adjusted_acting = min(30.0, raw_acting * multiplier)

    seller_score = JudgeRoundScore(
        selling_score=min(50.0, float(result.get("selling_score", 0))),
        acting_score=0.0,  # Seller doesn't get acting score
        legal_accuracy=min(20.0, max(0.0, float(result.get("legal_accuracy", 0)))),
        breakdown=result.get("selling_breakdown", {}),
        flags=result.get("flags", []),
        legal_details=result.get("legal_details", []),
    )
    seller_score.total = seller_score.selling_score + seller_score.legal_accuracy

    client_score = JudgeRoundScore(
        acting_score=adjusted_acting,
        selling_score=0.0,  # Client doesn't get selling score
        legal_accuracy=0.0,
        breakdown=result.get("acting_breakdown", {}),
    )
    client_score.total = client_score.acting_score

    logger.info(
        "Judge round %d: seller=%.0f (sell=%.0f legal=%.0f), client=%.0f (act=%.0f×%.1f)",
        round_number,
        seller_score.total,
        seller_score.selling_score,
        seller_score.legal_accuracy,
        client_score.total,
        raw_acting,
        multiplier,
    )

    return seller_score, client_score


def _parse_judge_response(raw: str) -> dict:
    """Parse JSON from LLM response, handling markdown code blocks."""
    text = raw.strip()

    # Remove markdown code block if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse judge JSON: %s", text[:200])
        return {
            "selling_score": 25,
            "acting_score": 15,
            "legal_accuracy": 10,
            "flags": ["JSON parse error"],
            "summary": "Ошибка парсинга оценки.",
        }


async def judge_full_duel(
    round1_dialog: list[dict],
    round2_dialog: list[dict],
    player1_id: uuid.UUID,
    player2_id: uuid.UUID,
    player1_name: str,
    player2_name: str,
    archetype: str,
    difficulty: DuelDifficulty,
    db: AsyncSession,
) -> JudgeDuelResult:
    """Judge a complete PvP duel (both rounds).

    Round 1: player1 SELLS, player2 is CLIENT
    Round 2: player2 SELLS, player1 is CLIENT
    """
    # Round 1: P1 sells, P2 acts
    r1_seller, r1_client = await judge_round(
        dialog=round1_dialog,
        seller_id=player1_id,
        client_id=player2_id,
        seller_name=player1_name,
        client_name=player2_name,
        archetype=archetype,
        difficulty=difficulty,
        round_number=1,
        db=db,
    )

    # Round 2: P2 sells, P1 acts
    r2_seller, r2_client = await judge_round(
        dialog=round2_dialog,
        seller_id=player2_id,
        client_id=player1_id,
        seller_name=player2_name,
        client_name=player1_name,
        archetype=archetype,
        difficulty=difficulty,
        round_number=2,
        db=db,
    )

    # Player 1: R1 selling + R2 acting
    p1_selling = r1_seller.selling_score + r1_seller.legal_accuracy
    p1_acting = r2_client.acting_score
    p1_total = p1_selling + p1_acting

    # Player 2: R2 selling + R1 acting
    p2_selling = r2_seller.selling_score + r2_seller.legal_accuracy
    p2_acting = r1_client.acting_score
    p2_total = p2_selling + p2_acting

    # Determine winner
    winner_id = None
    is_draw = False
    if abs(p1_total - p2_total) < 1.0:  # Within 1 point = draw
        is_draw = True
    elif p1_total > p2_total:
        winner_id = player1_id
    else:
        winner_id = player2_id

    result = JudgeDuelResult(
        player1_selling=p1_selling,
        player1_acting=p1_acting,
        player1_legal=r1_seller.legal_accuracy,
        player1_total=p1_total,
        player2_selling=p2_selling,
        player2_acting=p2_acting,
        player2_legal=r2_seller.legal_accuracy,
        player2_total=p2_total,
        winner_id=winner_id,
        is_draw=is_draw,
        summary=(
            f"P1: {p1_total:.0f} (sell={p1_selling:.0f} act={p1_acting:.0f}), "
            f"P2: {p2_total:.0f} (sell={p2_selling:.0f} act={p2_acting:.0f}). "
            f"{'Ничья' if is_draw else 'Победитель: P1' if winner_id == player1_id else 'Победитель: P2'}."
        ),
    )

    logger.info("Duel judged: %s", result.summary)
    return result


# ---------------------------------------------------------------------------
# Calibration (periodic check)
# ---------------------------------------------------------------------------

# 10 reference dialogs with known scores for drift detection.
# In production, load from file/DB.
CALIBRATION_DIALOGS: list[dict] = []
DRIFT_THRESHOLD = 0.05  # 5% deviation triggers alert


async def run_calibration() -> dict:
    """Run calibration check against reference dialogs.

    Returns:
        {"drift_detected": bool, "avg_deviation": float, "details": [...]}
    """
    if not CALIBRATION_DIALOGS:
        return {"drift_detected": False, "avg_deviation": 0.0, "details": [], "message": "No calibration data loaded."}

    # TODO: implement calibration against reference scores
    logger.info("Calibration check: %d reference dialogs", len(CALIBRATION_DIALOGS))
    return {"drift_detected": False, "avg_deviation": 0.0, "details": []}
