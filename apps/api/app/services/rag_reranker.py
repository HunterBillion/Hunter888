"""LLM-as-reranker using navy (Claude haiku-4.5 — cheap, fast, structured).

Why not a cross-encoder (bge-reranker-v2-m3 / ColBERT):
  - No local GPU and no HF Inference API key in this project.
  - LLM rerank is +1 cheap call (~200-500 ms with haiku-4.5), acceptable for
    the legal RAG path which runs once per AI Coach / Knowledge Quiz question.
  - Results come with rationale field we can log for debugging retrieval.

Pipeline:
  query + list of candidate fact_texts → LLM ranks them with JSON output:
    [{"idx": 0, "score": 0.92}, {"idx": 3, "score": 0.81}, ...]

Score semantics: [0, 1], where:
  ≥ 0.80 — highly relevant, cite directly
  0.55–0.80 — relevant, worth showing as context
  < 0.55 — borderline, confidence gate should refuse

Falls back to RRF-ordered list on LLM failure (rerank is best-effort).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.services.rag_legal import RAGResult

logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────

RERANKER_MODEL = "claude-haiku-4.5"
RERANKER_TIMEOUT_S = 15.0
MAX_CANDIDATES = 20         # cap input size
MAX_SNIPPET_CHARS = 800     # per candidate
MAX_QUERY_CHARS = 500

_SYSTEM_PROMPT = (
    "Ты — эксперт-юрист по 127-ФЗ о банкротстве. Твоя задача — оценить "
    "РЕЛЕВАНТНОСТЬ каждого юридического фрагмента к заданному вопросу.\n"
    "\n"
    "Для каждого фрагмента поставь оценку от 0.0 до 1.0:\n"
    " - 1.0 — прямо отвечает на вопрос\n"
    " - 0.8 — содержит ответ, но с дополнительной информацией\n"
    " - 0.6 — смежная тема, контекстно полезно\n"
    " - 0.4 — упоминает ключевые слова, но не отвечает на вопрос\n"
    " - 0.0 — не связан с вопросом\n"
    "\n"
    "Ответь ТОЛЬКО JSON-массивом без дополнительного текста:\n"
    '[{"idx": 0, "score": 0.82}, {"idx": 1, "score": 0.45}, ...]\n'
    "Включи ВСЕ фрагменты (по их idx), в любом порядке. Никакого комментария вне JSON."
)


# ─── HTTP client (reuses navy LLM endpoint) ──────────────────────────────

_HTTP: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _HTTP
    if _HTTP is None or _HTTP.is_closed:
        _HTTP = httpx.AsyncClient(timeout=RERANKER_TIMEOUT_S)
    return _HTTP


# ─── LLM call ────────────────────────────────────────────────────────────


async def _call_llm(user_prompt: str) -> str | None:
    url_base = os.environ.get("LOCAL_LLM_URL", "https://api.navy/v1").rstrip("/")
    api_key = os.environ.get("LOCAL_LLM_API_KEY", "")
    if not api_key:
        logger.warning("rag_reranker: LOCAL_LLM_API_KEY missing")
        return None
    try:
        r = await _get_client().post(
            f"{url_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": RERANKER_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 500,
            },
        )
        if r.status_code != 200:
            logger.warning("rag_reranker HTTP %d: %s", r.status_code, r.text[:200])
            return None
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("rag_reranker LLM call failed: %s", exc)
        return None


# ─── JSON score parser (robust to markdown fences and extra text) ────────


_JSON_ARRAY_RE = re.compile(r"\[\s*\{.*?\}\s*\]", re.DOTALL)


def _parse_scores(raw: str) -> list[tuple[int, float]]:
    """Extract [(idx, score), ...] from LLM output, robust to noise."""
    if not raw:
        return []
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)

    # Find the JSON array
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        logger.warning("rag_reranker: no JSON array in LLM output: %s", text[:200])
        return []

    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        logger.warning("rag_reranker JSON parse failed: %s (text=%s)", exc, match.group(0)[:200])
        return []

    out: list[tuple[int, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("idx")
        score = item.get("score")
        if not isinstance(idx, int):
            continue
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        score = max(0.0, min(1.0, score))
        out.append((idx, score))
    return out


# ─── Public API ──────────────────────────────────────────────────────────


async def rerank_with_llm(
    query: str,
    candidates: list["RAGResult"],
    *,
    target_top_k: int = 5,
) -> list["RAGResult"]:
    """Re-rank candidates via LLM relevance scoring.

    On failure (LLM error, parse error, model doesn't return scores for all
    candidates), returns the input list UNCHANGED — RRF ranking is the
    fallback.

    Only top `MAX_CANDIDATES` candidates are sent to the LLM; if the input
    list is longer, the tail is preserved after reranked prefix.
    """
    if not candidates:
        return candidates
    if len(candidates) == 1:
        return candidates

    t0 = time.monotonic()

    # Cap input
    head = candidates[:MAX_CANDIDATES]
    tail = candidates[MAX_CANDIDATES:]

    # Build prompt
    q = query.strip()[:MAX_QUERY_CHARS]
    lines = [f"ВОПРОС: {q}", "", "ФРАГМЕНТЫ:"]
    for i, c in enumerate(head):
        snippet = c.fact_text[:MAX_SNIPPET_CHARS].replace("\n", " ").strip()
        cite = f" (Основание: {c.law_article})" if c.law_article else ""
        lines.append(f"[idx={i}] {snippet}{cite}")
    user_prompt = "\n".join(lines)

    raw = await _call_llm(user_prompt)
    if raw is None:
        logger.info("rag_reranker: LLM unavailable, keeping RRF order")
        return candidates

    scores = _parse_scores(raw)
    if not scores:
        logger.info("rag_reranker: no scores parsed, keeping RRF order")
        return candidates

    # Map idx → score; for candidates missing from LLM output, keep their RRF score
    score_map: dict[int, float] = {idx: score for idx, score in scores}
    ranked: list[tuple[int, float, "RAGResult"]] = []
    for i, c in enumerate(head):
        s = score_map.get(i)
        if s is None:
            # LLM didn't score this candidate — use RRF-derived score as fallback
            s = c.relevance_score * 0.8  # slightly penalized (LLM ignored it)
        ranked.append((i, s, c))

    ranked.sort(key=lambda t: t[1], reverse=True)

    # Build output — override relevance_score with LLM score so confidence
    # gate downstream uses the reranker output.
    from app.services.rag_legal import RAGResult as _RR
    reranked: list["RAGResult"] = []
    for _i, score, c in ranked:
        reranked.append(_RR(
            chunk_id=c.chunk_id,
            category=c.category,
            fact_text=c.fact_text,
            law_article=c.law_article,
            relevance_score=score,  # <-- override with LLM score
            common_errors=c.common_errors,
            correct_response_hint=c.correct_response_hint,
            difficulty_level=c.difficulty_level,
            is_court_practice=c.is_court_practice,
            court_case_reference=c.court_case_reference,
            question_templates=c.question_templates,
            follow_up_questions=c.follow_up_questions,
            blitz_question=c.blitz_question,
            blitz_answer=c.blitz_answer,
            tags=c.tags,
        ))

    # Trim to target_top_k but keep any tail that was never reranked
    out = reranked[:target_top_k]
    if tail and len(out) < target_top_k:
        out.extend(tail[: target_top_k - len(out)])

    ms = (time.monotonic() - t0) * 1000
    top_score = out[0].relevance_score if out else 0.0
    logger.info(
        "rag_reranker: %d → %d candidates in %.0fms, top_score=%.3f",
        len(head), len(out), ms, top_score,
    )
    return out


async def close_reranker_client() -> None:
    """Cleanup on app shutdown."""
    global _HTTP
    if _HTTP and not _HTTP.is_closed:
        await _HTTP.aclose()
    _HTTP = None
