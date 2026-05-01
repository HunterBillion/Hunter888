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
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import errors as err
from app.models.pvp import DuelDifficulty, DIFFICULTY_MULTIPLIERS
from app.services.arena_metrics import (
    ARENA_AI_JUDGE_LATENCY,
    ARENA_JUDGE_DEGRADED,
)
from app.services.llm import generate_response
from app.services.rag_legal import (
    retrieve_legal_context,
    RAGContext,
    log_chunk_usage,
    record_chunk_outcome,
)

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

    # Phase A (2026-04-20) — coaching payload propagated to all 5 Arena modes.
    # Populated by LLM judge when role == "seller". 1-2 sentence ideal line
    # the seller SHOULD have said, plus 127-ФЗ статьи to cite, plus a
    # short coaching hint. All are optional — fallback to flags/summary if
    # LLM didn't return them (old prompts).
    coaching_tip: str = ""           # "Подсказка: раскрой срок и порог долга сразу"
    ideal_reply: str = ""            # "Иван, при долге от 500т вы можете списать всё за 6 мес через суд..."
    key_articles: list[str] = field(default_factory=list)  # ["ст. 213.3", "ст. 213.28"]

    # PR F: True iff the judge fell back to the neutral 25/15/10 default
    # because the LLM call failed (timeout / safety-block / parse error /
    # all providers down). The caller must surface this to the player so a
    # fake score isn't shown as real. Today the fake score is silently
    # accepted by the FE — see ARENA_JUDGE_DEGRADED counter from PR B.
    degraded: bool = False
    degraded_reason: str = ""


@dataclass
class PlayerBreakdown:
    """Detailed per-player breakdown for post-duel analysis."""
    selling_score: float = 0.0
    acting_score: float = 0.0
    legal_score: float = 0.0
    total: float = 0.0
    selling_breakdown: dict = field(default_factory=dict)
    acting_breakdown: dict = field(default_factory=dict)
    legal_details: list[dict] = field(default_factory=list)
    best_reply: str = ""  # Highlighted best message
    recommendations: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


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

    # Post-duel breakdown (Task 2.5)
    player1_breakdown: PlayerBreakdown | None = None
    player2_breakdown: PlayerBreakdown | None = None
    turning_point: dict = field(default_factory=dict)  # {round, message_index, description}


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
  "summary": "<краткое резюме оценки на русском, 2-3 предложения>",
  "coaching_tip": "<1 короткая подсказка продавцу на русском, 1 предложение, 10-18 слов>",
  "ideal_reply": "<идеальная реплика продавца, которую он ДОЛЖЕН был сказать в ключевой момент, 1-2 предложения, с конкретикой 127-ФЗ>",
  "key_articles": ["<статьи 127-ФЗ, которые стоило процитировать, в формате 'ст. 213.3' или 'ст. 71'; 1-3 элемента>"]
}}"""

JUDGE_USER_PROMPT = """## Контекст дуэли
- Раунд: {round_number}/2
- Сложность клиента: {difficulty} (множитель acting: ×{multiplier})
- Роль ПРОДАВЦА: {seller_name}
- Роль КЛИЕНТА: {client_name}
- Архетип клиента: {archetype}

{emotion_context}
## Диалог раунда:
{dialog}

Оцени ПРОДАВЦА по selling_score и legal_accuracy.
Оцени КЛИЕНТА по acting_score.
Учти эмоциональную динамику клиента при оценке acting_score.
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
    emotion_journey: dict | None = None,
    # Content→Arena PR-5 — optional duel_id for chunk-usage telemetry.
    # When provided, every legal chunk surfaced by the RAG retrieval is
    # logged with ``source_type="pvp_duel"`` so methodologists can see
    # which uploaded chunks actually fire in arena play. Omitted in
    # legacy callers (calibration, ad-hoc replay) — telemetry is then
    # silently skipped.
    duel_id: uuid.UUID | None = None,
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
        emotion_journey: optional emotion timeline from client player

    Returns:
        (seller_score, client_score) as JudgeRoundScore
    """
    # Collect all messages for legal RAG context
    all_text = " ".join(msg.get("text", "") for msg in dialog)
    legal_context = await retrieve_legal_context(all_text, db, top_k=5)

    # Content→Arena PR-5: log retrieval for every chunk surfaced by the
    # RAG. Methodologists in AiQualityPanel can then see "which 127-ФЗ
    # chunks actually fire in dueled rounds" — closes the feedback loop
    # for ROP-uploaded knowledge. Logger is non-blocking (own try/except
    # inside log_chunk_usage); a logging failure never breaks the judge.
    if duel_id is not None and legal_context.has_results:
        try:
            await log_chunk_usage(
                db,
                chunk_ids=[r.chunk_id for r in legal_context.results if r.chunk_id is not None],
                user_id=seller_id,  # the player whose answer the chunk would have helped
                source_type="pvp_duel",
                source_id=duel_id,
                query_text=all_text,
                retrieval_method=legal_context.method,
                relevance_scores={r.chunk_id: r.relevance_score for r in legal_context.results if r.chunk_id is not None},
                ranks={r.chunk_id: i for i, r in enumerate(legal_context.results, start=1) if r.chunk_id is not None},
            )
        except Exception:
            logger.warning("pvp_judge: log_chunk_usage failed (non-critical)", exc_info=True)

    # Format dialog
    dialog_text = ""
    for msg in dialog:
        role_label = "ПРОДАВЕЦ" if msg.get("role") == "seller" else "КЛИЕНТ"
        dialog_text += f"[{role_label}]: {msg.get('text', '')}\n"

    multiplier = DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)

    # Format emotion context if available
    emotion_context = ""
    if emotion_journey:
        timeline = emotion_journey.get("timeline", [])
        summary = emotion_journey.get("summary", {})
        if timeline:
            states = [e.get("state", "?") for e in timeline[:12]]
            emotion_context = (
                f"## Эмоциональная динамика клиента\n"
                f"- Путь: {' → '.join(states)}\n"
                f"- Переходов: {summary.get('total_transitions', 0)}, "
                f"откатов: {summary.get('rollbacks', 0)}, "
                f"пик: {summary.get('peak_state', 'N/A')}\n"
            )
            turning_points = summary.get("turning_points", [])
            if turning_points:
                tp = turning_points[0]
                emotion_context += (
                    f"- Перелом: {tp.get('from_state', '?')} → {tp.get('to_state', '?')} "
                    f"(msg #{tp.get('message_index', '?')})\n"
                )

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
        emotion_context=emotion_context,
        dialog=dialog_text,
    )

    # LLM call (temperature controlled by system prompt directive for determinism)
    _judge_started = time.time()
    # PR F: track fallback so the WS layer can emit ``judge.degraded`` and
    # the FE can show "оценка не выполнена, применены резервные баллы"
    # instead of accepting the neutral 25/15/10 as a real score.
    _degraded = False
    _degraded_reason = ""
    try:
        messages = [{"role": "user", "content": user}]
        llm_response = await generate_response(
            system_prompt=system,
            messages=messages,
            task_type="judge",
            prefer_provider="cloud",
            # PR E: judge needs determinism. Module docstring (line 10)
            # promises "Temperature = 0 (deterministic)" but the original
            # call used the provider default (~0.85) → scores oscillated
            # ±5–10 between identical inputs. 0.2 keeps a tiny bit of
            # variance so drift-detection in run_calibration still surfaces
            # semantic regressions. max_tokens=600 caps the response: the
            # judge schema fits in <600 tokens and longer outputs were
            # filtered post-hoc, wasting cloud budget.
            temperature=0.2,
            max_tokens=600,
        )

        # Parse JSON from response
        result = _parse_judge_response(llm_response.content)
        ARENA_AI_JUDGE_LATENCY.labels(judge_type="round", status="ok").observe(time.time() - _judge_started)
        # _parse_judge_response uses the same neutral 25/15/10 sentinel on
        # JSON parse failure (after logging a warning). Detect it via the
        # canonical "JSON parse error" flag the parser writes.
        _flags_check = result.get("flags") or []
        if isinstance(_flags_check, list) and "JSON parse error" in _flags_check:
            _degraded = True
            _degraded_reason = "json_parse"

    except Exception as e:
        logger.error("AI Judge failed: %s", e)
        ARENA_AI_JUDGE_LATENCY.labels(judge_type="round", status="error").observe(time.time() - _judge_started)
        ARENA_JUDGE_DEGRADED.labels(reason="llm_error").inc()
        _degraded = True
        _degraded_reason = "llm_error"
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

    # Phase A — coaching payload (2026-04-20). Pulled straight from judge
    # output; if LLM omitted them (older prompt / fallback), we derive a
    # gentle fallback from legal_details + flags so the fronted isn't blank.
    coaching_tip_raw = str(result.get("coaching_tip") or "").strip()
    ideal_reply_raw = str(result.get("ideal_reply") or "").strip()
    raw_articles = result.get("key_articles") or []
    if not isinstance(raw_articles, list):
        raw_articles = []
    key_articles: list[str] = [
        str(a).strip() for a in raw_articles if str(a).strip()
    ][:3]

    # Fallback: distil articles from legal_details if judge forgot
    if not key_articles:
        for detail in result.get("legal_details", []) or []:
            claim = str(detail.get("claim") or "")
            if "ст." in claim or "ФЗ" in claim:
                key_articles.append(claim[:64])
            if len(key_articles) >= 3:
                break

    # Fallback coaching: first flag or summary fragment
    if not coaching_tip_raw:
        flags_list = result.get("flags", []) or []
        if flags_list:
            coaching_tip_raw = str(flags_list[0])[:160]
        else:
            coaching_tip_raw = str(result.get("summary") or "")[:160]

    seller_score = JudgeRoundScore(
        selling_score=min(50.0, float(result.get("selling_score", 0))),
        acting_score=0.0,  # Seller doesn't get acting score
        legal_accuracy=min(20.0, max(0.0, float(result.get("legal_accuracy", 0)))),
        breakdown=result.get("selling_breakdown", {}),
        flags=result.get("flags", []),
        legal_details=result.get("legal_details", []),
        coaching_tip=coaching_tip_raw[:240],
        ideal_reply=ideal_reply_raw[:400],
        key_articles=key_articles,
        degraded=_degraded,
        degraded_reason=_degraded_reason,
    )
    seller_score.total = seller_score.selling_score + seller_score.legal_accuracy

    client_score = JudgeRoundScore(
        acting_score=adjusted_acting,
        selling_score=0.0,  # Client doesn't get selling score
        legal_accuracy=0.0,
        breakdown=result.get("acting_breakdown", {}),
        degraded=_degraded,
        degraded_reason=_degraded_reason,
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

    # Content→Arena PR-5: record per-chunk outcome so methodology gets
    # answer_correct telemetry. Heuristic: a chunk is "answered correctly"
    # if the judge's legal_details list contains ANY entry with a matching
    # ``law_article`` whose accuracy is "correct" or "correct_cited", and
    # "incorrect" otherwise. Skipped on degraded judge (no real eval).
    if duel_id is not None and not _degraded and legal_context.has_results:
        try:
            details_list = result.get("legal_details") or []
            article_accuracy: dict[str, bool] = {}
            for d in details_list if isinstance(details_list, list) else []:
                claim = str((d or {}).get("claim") or "")
                accuracy = str((d or {}).get("accuracy") or "").lower()
                # Normalise the article reference (e.g. "ст. 213.3") so we
                # can match against retrieved chunks' law_article field.
                if not claim:
                    continue
                is_correct = accuracy in ("correct", "correct_cited")
                # Fold multiple mentions: any "correct" wins; otherwise "incorrect".
                for r in legal_context.results:
                    if r.law_article and r.law_article.lower() in claim.lower():
                        if is_correct:
                            article_accuracy[str(r.chunk_id)] = True
                        else:
                            article_accuracy.setdefault(str(r.chunk_id), False)

            for r in legal_context.results:
                if r.chunk_id is None:
                    continue
                outcome = article_accuracy.get(str(r.chunk_id))
                if outcome is None:
                    # Chunk surfaced by RAG but not addressed in legal_details
                    # — treat as not-yet-answered (was_answered stays False
                    # via log_chunk_usage's default).
                    continue
                await record_chunk_outcome(
                    db,
                    chunk_id=r.chunk_id,
                    user_id=seller_id,
                    source_type="pvp_duel",
                    source_id=duel_id,
                    answer_correct=outcome,
                    score_delta=float(seller_score.legal_accuracy),
                )
        except Exception:
            logger.warning("pvp_judge: record_chunk_outcome failed (non-critical)", exc_info=True)

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
        ARENA_JUDGE_DEGRADED.labels(reason="json_parse").inc()
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
    round1_emotion_journey: dict | None = None,
    round2_emotion_journey: dict | None = None,
    # Content→Arena PR-5: forwarded into per-round judge_round so the
    # chunk-usage telemetry tags the duel correctly. Optional for
    # back-compat with older callers (calibration, replay).
    duel_id: uuid.UUID | None = None,
) -> JudgeDuelResult:
    """Judge a complete PvP duel (both rounds).

    Round 1: player1 SELLS, player2 is CLIENT
    Round 2: player2 SELLS, player1 is CLIENT
    """
    _full_started = time.time()
    # Round 1: P1 sells, P2 acts (P2's emotion journey)
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
        emotion_journey=round1_emotion_journey,
        duel_id=duel_id,
    )

    # Round 2: P2 sells, P1 acts (P1's emotion journey)
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
        emotion_journey=round2_emotion_journey,
        duel_id=duel_id,
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

    # Build per-player breakdowns
    p1_breakdown = PlayerBreakdown(
        selling_score=r1_seller.selling_score,
        acting_score=r2_client.acting_score,
        legal_score=r1_seller.legal_accuracy,
        total=p1_total,
        selling_breakdown=r1_seller.breakdown,
        acting_breakdown=r2_client.breakdown,
        legal_details=r1_seller.legal_details,
        flags=r1_seller.flags,
    )
    p2_breakdown = PlayerBreakdown(
        selling_score=r2_seller.selling_score,
        acting_score=r1_client.acting_score,
        legal_score=r2_seller.legal_accuracy,
        total=p2_total,
        selling_breakdown=r2_seller.breakdown,
        acting_breakdown=r1_client.breakdown,
        legal_details=r2_seller.legal_details,
        flags=r2_seller.flags,
    )

    # Find best reply per player and turning point
    _find_best_reply(round1_dialog, round2_dialog, p1_breakdown, p2_breakdown, player1_id, player2_id)
    turning_point = _find_turning_point(round1_dialog, round2_dialog, r1_seller, r2_seller)

    # Generate recommendations
    p1_breakdown.recommendations = _generate_recommendations(p1_breakdown, "seller")
    p2_breakdown.recommendations = _generate_recommendations(p2_breakdown, "seller")

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
        player1_breakdown=p1_breakdown,
        player2_breakdown=p2_breakdown,
        turning_point=turning_point,
    )

    ARENA_AI_JUDGE_LATENCY.labels(judge_type="duel", status="ok").observe(time.time() - _full_started)
    logger.info("Duel judged: %s", result.summary)
    return result


def _find_best_reply(
    r1_dialog: list[dict],
    r2_dialog: list[dict],
    p1_bd: PlayerBreakdown,
    p2_bd: PlayerBreakdown,
    player1_id: uuid.UUID,
    player2_id: uuid.UUID,
) -> None:
    """Find best reply for each player (longest substantive message in seller role)."""
    # P1 is seller in R1
    p1_seller_msgs = [
        msg.get("text", "") for msg in r1_dialog
        if msg.get("role") == "seller" and len(msg.get("text", "")) > 30
    ]
    if p1_seller_msgs:
        p1_bd.best_reply = max(p1_seller_msgs, key=len)[:300]

    # P2 is seller in R2
    p2_seller_msgs = [
        msg.get("text", "") for msg in r2_dialog
        if msg.get("role") == "seller" and len(msg.get("text", "")) > 30
    ]
    if p2_seller_msgs:
        p2_bd.best_reply = max(p2_seller_msgs, key=len)[:300]


def _find_turning_point(
    r1_dialog: list[dict],
    r2_dialog: list[dict],
    r1_seller_score: JudgeRoundScore,
    r2_seller_score: JudgeRoundScore,
) -> dict:
    """Identify the turning point of the duel."""
    # The turning point is where one player pulled ahead
    r1_total = r1_seller_score.total
    r2_total = r2_seller_score.total
    diff = abs(r1_total - r2_total)

    if diff < 3:
        return {"description": "Равная дуэль — оба участника показали сопоставимый уровень."}

    if r1_total > r2_total:
        # P1 dominated in selling (R1)
        dominant_round = 1
        dominant_area = "продажах"
        if r1_seller_score.breakdown.get("objection_handling", 0) > 10:
            dominant_area = "работе с возражениями"
        elif r1_seller_score.breakdown.get("closing", 0) > 7:
            dominant_area = "закрытии сделки"
    else:
        dominant_round = 2
        dominant_area = "продажах"
        if r2_seller_score.breakdown.get("objection_handling", 0) > 10:
            dominant_area = "работе с возражениями"
        elif r2_seller_score.breakdown.get("closing", 0) > 7:
            dominant_area = "закрытии сделки"

    return {
        "round": dominant_round,
        "description": f"Перелом в раунде {dominant_round}: решающее преимущество в {dominant_area}.",
    }


def _generate_recommendations(breakdown: PlayerBreakdown, role: str) -> list[str]:
    """Generate 2-3 recommendations based on score breakdown."""
    recs: list[str] = []
    sb = breakdown.selling_breakdown

    if sb.get("objection_handling", 15) < 8:
        recs.append("Усильте работу с возражениями: выявляйте истинное возражение перед обработкой.")
    if sb.get("persuasion", 10) < 5:
        recs.append("Повысьте убедительность: используйте конкретные цифры и социальное доказательство.")
    if sb.get("closing", 10) < 5:
        recs.append("Улучшите закрытие: предлагайте конкретный следующий шаг.")
    if sb.get("structure", 10) < 5:
        recs.append("Работайте над структурой: выявление потребности → презентация → закрытие.")
    if breakdown.legal_score < 10:
        recs.append("Повторите юридическую базу 127-ФЗ: ссылки на конкретные статьи повышают доверие.")

    ab = breakdown.acting_breakdown
    if ab.get("archetype_authenticity", 10) < 5:
        recs.append("Глубже изучите архетипы клиентов для более убедительной игры.")

    return recs[:3]


# ---------------------------------------------------------------------------
# Calibration (periodic check)
# ---------------------------------------------------------------------------

# Baseline calibration dialogs with expert-scored references.
# Each entry: a pair of player messages + expected score breakdown.
# Used for drift detection: if judge deviates > DRIFT_THRESHOLD from reference,
# alert is raised and scoring weights may need adjustment.
CALIBRATION_DIALOGS: list[dict] = [
    {
        "id": "cal-001",
        "scenario": "cold_call_basic",
        "player_messages": [
            "Добрый день! Меня зовут Алексей, компания ЮрКонсалт. Хотел бы обсудить вашу ситуацию с задолженностью.",
            "Понимаю ваши опасения. Банкротство физических лиц по 127-ФЗ — это законный способ списания долгов. Позвольте объяснить.",
        ],
        "expected_selling": 35.0,
        "expected_acting": 18.0,
        "expected_legal": 14.0,
        "expected_total": 67.0,
        "difficulty": "normal",
    },
    {
        "id": "cal-002",
        "scenario": "objection_price",
        "player_messages": [
            "Я вас слышу, цена действительно важна. Давайте посчитаем: ваш долг 2 миллиона, ежемесячные платежи 45 тысяч.",
            "По статье 213.3 закона о банкротстве, минимальный долг для подачи — 500 тысяч. Ваш случай полностью подходит.",
        ],
        "expected_selling": 40.0,
        "expected_acting": 22.0,
        "expected_legal": 17.0,
        "expected_total": 79.0,
        "difficulty": "normal",
    },
    {
        "id": "cal-003",
        "scenario": "weak_performance",
        "player_messages": [
            "Ну... здравствуйте. Я вот звоню по поводу... ну, банкротства.",
            "Это когда долги списывают. Не знаю точно какая статья, но это законно.",
        ],
        "expected_selling": 12.0,
        "expected_acting": 8.0,
        "expected_legal": 3.0,
        "expected_total": 23.0,
        "difficulty": "normal",
    },
    {
        "id": "cal-004",
        "scenario": "expert_level",
        "player_messages": [
            "Марина Ивановна, я изучил вашу ситуацию. С долгом в 3.5 миллиона и залоговым имуществом нам нужна стратегия реструктуризации по статье 213.11 с последующим переходом к реализации.",
            "Обратите внимание: по определению ВС РФ 304-ЭС16-14541, единственное жильё защищено исполнительским иммунитетом. Ваша квартира не будет затронута процедурой.",
        ],
        "expected_selling": 46.0,
        "expected_acting": 26.0,
        "expected_legal": 19.0,
        "expected_total": 91.0,
        "difficulty": "hard",
    },
    {
        "id": "cal-005",
        "scenario": "hostile_client",
        "player_messages": [
            "Понимаю вашу реакцию. Давайте я коротко: закон 127-ФЗ дает вам право списать долги законно, без последствий для семьи.",
            "Мне не нужно ничего продавать. Моя задача — дать вам информацию. Решение за вами. Могу перезвонить, когда будет удобно.",
        ],
        "expected_selling": 38.0,
        "expected_acting": 24.0,
        "expected_legal": 12.0,
        "expected_total": 74.0,
        "difficulty": "hard",
    },
]

DRIFT_THRESHOLD = 0.05  # 5% deviation triggers alert

# Baseline scoring weights (can be adjusted based on calibration results)
SCORING_WEIGHTS = {
    "selling": {"objection_handling": 0.3, "persuasion": 0.25, "structure": 0.25, "closing": 0.2},
    "acting": {"role_authenticity": 0.4, "emotional_depth": 0.3, "realism": 0.3},
    "legal": {"accuracy": 0.5, "citation": 0.3, "relevance": 0.2},
}


async def run_calibration() -> dict:
    """Run calibration check against reference dialogs.

    Compares judge output against expected scores for 5 reference dialogs.
    Returns drift metrics for monitoring and weight adjustment.
    """
    if not CALIBRATION_DIALOGS:
        return {"drift_detected": False, "avg_deviation": 0.0, "details": [], "message": err.NO_CALIBRATION_DATA}

    logger.info("Calibration check: %d reference dialogs", len(CALIBRATION_DIALOGS))
    details = []
    total_deviation = 0.0

    for dialog in CALIBRATION_DIALOGS:
        try:
            # Build a minimal judge prompt and score via LLM
            combined_text = "\n".join(dialog["player_messages"])
            difficulty = DuelDifficulty(dialog["difficulty"])
            diff_mult = DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)

            prompt = (
                f"Оцени реплики менеджера по продажам банкротства ФЗ-127 по 3 критериям:\n"
                f"1) selling_score (0-50): работа с возражениями, убеждение, структура, закрытие\n"
                f"2) acting_score (0-30): аутентичность роли, эмоциональная глубина\n"
                f"3) legal_accuracy (0-20): точность юридических ссылок\n"
                f"Сложность: {difficulty.value} (множитель acting: {diff_mult})\n\n"
                f"Реплики:\n{combined_text}\n\n"
                f"Ответ ТОЛЬКО JSON: {{\"selling\": N, \"acting\": N, \"legal\": N}}"
            )
            resp = await generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="Ты AI-судья PvP-арены. Отвечай строго JSON.",
                temperature=0,
                max_tokens=100,
                task_type="structured",
                prefer_provider="local",
            )
            # Parse JSON from response
            import re
            json_match = re.search(r'\{[^}]+\}', resp)
            if json_match:
                scores = json.loads(json_match.group())
                actual_total = scores.get("selling", 0) + scores.get("acting", 0) * diff_mult + scores.get("legal", 0)
            else:
                actual_total = dialog["expected_total"]
                scores = {"selling": 0, "acting": 0, "legal": 0}

            expected_total = dialog["expected_total"]
            deviation = abs(actual_total - expected_total) / max(expected_total, 1)

            details.append({
                "id": dialog["id"],
                "expected": expected_total,
                "actual": round(actual_total, 1),
                "deviation": round(deviation, 3),
                "selling_diff": round(scores.get("selling", 0) - dialog["expected_selling"], 1),
                "acting_diff": round(scores.get("acting", 0) - dialog["expected_acting"], 1),
                "legal_diff": round(scores.get("legal", 0) - dialog["expected_legal"], 1),
            })
            total_deviation += deviation
        except Exception as e:
            details.append({"id": dialog["id"], "error": str(e)})

    avg_deviation = total_deviation / len(CALIBRATION_DIALOGS) if CALIBRATION_DIALOGS else 0
    drift_detected = avg_deviation > DRIFT_THRESHOLD

    if drift_detected:
        logger.warning(
            "Judge calibration DRIFT detected: avg_deviation=%.1f%% (threshold=%.1f%%)",
            avg_deviation * 100, DRIFT_THRESHOLD * 100,
        )

    return {
        "drift_detected": drift_detected,
        "avg_deviation": round(avg_deviation, 4),
        "details": details,
        "scoring_weights": SCORING_WEIGHTS,
    }
