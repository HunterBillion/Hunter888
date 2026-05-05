"""P3 — Cross-session AI client memory.

When a manager re-calls the SAME real CRM client (``real_client_id``)
the AI persona used to start cold every time — fresh ``ClientProfile``,
fresh emotion, no recollection of the prior call. From the user's POV
the "client" was a goldfish.

This module fixes that by producing a 1-3 sentence Russian summary of
the **most recent COMPLETED training session** for ``(user_id,
real_client_id)`` and exposing two integration hooks:

* :func:`fetch_last_session_summary` — returns the summary string (or
  None when there is no prior session). Cached in Redis for 1h with
  key ``xsession:summary:{user_id}:{real_client_id}``.
* :func:`extract_closing_emotion` — pulls the closing emotion out of
  ``TrainingSession.emotion_timeline`` so the WS bootstrap can seed
  the new session's emotion engine one notch warmer than ``cold``
  when the previous call ended hostile/callback/hangup.
* :func:`evict_summary_cache` — called from
  :func:`completion_policy.finalize_training_session` after a session
  closes so the next start reads fresh data instead of stale cache.

The summary deliberately reads from already-persisted columns
(``terminal_outcome``, ``score_total``, ``scoring_details.judge``,
``emotion_timeline``). No new schema, no migration. Persona behaviour
is shaped by injecting the summary into ``_build_system_prompt``
under a new ``client_history`` parameter — parallel to the existing
``persona_facts`` block from TZ-4.5 PR 4.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training import SessionStatus, TrainingSession

logger = logging.getLogger(__name__)


# ── Constants ───────────────────────────────────────────────────────────

#: Redis cache TTL for fetched summaries. 1h is short enough that a
#: completing session evicting the key is the *common* path, but long
#: enough that the same user opening the CRM card twice in 30 seconds
#: doesn't double-hit Postgres.
_CACHE_TTL_SECONDS = 60 * 60

#: Hard cap on the rendered summary so a long judge rationale can't
#: blow the system-prompt budget.
_MAX_SUMMARY_CHARS = 300

#: Closing emotions that should warm the next session's seed by one
#: notch (i.e. start "cold" instead of letting the engine pick a
#: deeper "hostile" baseline). Anything outside this set keeps the
#: default cold-call seed — a returning friendly client still gets
#: cold-call expectation because the manager is "trying again".
WARMING_CLOSING_EMOTIONS = frozenset({"hostile", "hangup", "callback"})


# ── Public helpers ──────────────────────────────────────────────────────


def cache_key(user_id: uuid.UUID, real_client_id: uuid.UUID) -> str:
    """Canonical Redis key for a (manager, real-client) pair."""
    return f"xsession:summary:{user_id}:{real_client_id}"


def extract_closing_emotion(emotion_timeline: Any) -> str | None:
    """Return the last emotion state from ``TrainingSession.emotion_timeline``.

    The column shape evolved over time:

    * Early v5 sessions stored a list of dicts ``[{"state": ...}, ...]``.
    * Later sessions wrap it in a dict ``{"events": [...]}``.

    Both shapes are tolerated. Anything we cannot parse returns None
    so the seed-warming branch falls back to defaults.
    """
    if not emotion_timeline:
        return None
    events: list[Any]
    if isinstance(emotion_timeline, list):
        events = emotion_timeline
    elif isinstance(emotion_timeline, dict):
        raw = (
            emotion_timeline.get("events")
            or emotion_timeline.get("entries")
            or emotion_timeline.get("timeline")
        )
        if isinstance(raw, list):
            events = raw
        else:
            return None
    else:
        return None

    for entry in reversed(events):
        if isinstance(entry, dict):
            state = entry.get("state") or entry.get("emotion")
            if isinstance(state, str) and state.strip():
                return state.strip().lower()
    return None


def _humanize_age(prior_completed_at: datetime | None) -> str:
    """Render "вчера" / "N дней назад" / "сегодня" / "давно" for the
    summary opener."""
    if prior_completed_at is None:
        return "недавно"
    now = datetime.now(timezone.utc)
    if prior_completed_at.tzinfo is None:
        prior_completed_at = prior_completed_at.replace(tzinfo=timezone.utc)
    delta = now - prior_completed_at
    days = delta.days
    if days <= 0:
        return "сегодня"
    if days == 1:
        return "вчера"
    if days < 7:
        return f"{days} дн. назад"
    if days < 30:
        weeks = days // 7
        return f"{weeks} нед. назад"
    months = max(1, days // 30)
    return f"{months} мес. назад"


def _format_outcome(outcome: str | None) -> str:
    """Map ``TerminalOutcome.value`` to a short Russian phrase."""
    if not outcome:
        return "разговор оборвался"
    mapping = {
        "deal_signed": "договорились по сделке",
        "deal": "договорились",
        "callback_scheduled": "договорились перезвонить",
        "callback": "попросил перезвонить",
        "rejected": "отказался",
        "objection_blocked": "не пробил возражения",
        "no_decision": "не принял решение",
        "client_hangup": "бросил трубку",
        "manager_hangup": "менеджер сам положил трубку",
        "abandoned": "клиент ушёл",
        "timeout": "разговор затянулся, прервался",
    }
    return mapping.get(outcome, outcome.replace("_", " "))


# PR-A.1 (audit fix from prod feedback): user opened the banner and
# said «очень мало контекста — главный вопрос, будет ли AI помнить
# факты». The original summary was outcome+score+emotion only — the
# AI knew the call ended badly but not WHY. These extractors mine the
# transcript so the next session's LLM gets the substance.

# Manager-promise patterns. Conservative — false positives in a system
# prompt make the AI accuse the manager of breaking promises that
# never existed. Patterns lowercased; matched on raw lower text.
_PROMISE_PATTERNS = (
    "отправлю", "отправим", "пришлю", "пришлём", "вышлю", "вышлем",
    "перезвоню", "перезвоним", "позвоню завтра", "позвоню позже",
    "наберу вас", "напишу", "подготовлю", "составлю", "согласую",
    "уточню и вернусь", "уточню и перезвоню",
    "договоримся на завтра", "созвонимся завтра", "созвонимся позже",
)

# Client-objection patterns. Same conservative bias.
_OBJECTION_PATTERNS = (
    ("дорого", "цена/деньги"),
    ("это сколько", "цена/деньги"),
    ("нет денег", "цена/деньги"),
    ("не нужно", "не нужно"),
    ("не интересно", "не нужно"),
    ("посоветуюсь", "нужно посоветоваться"),
    ("посоветоваться", "нужно посоветоваться"),
    ("обсудить с", "нужно посоветоваться"),
    ("подумать", "нужно подумать"),
    ("не сейчас", "не сейчас"),
    ("позже", "не сейчас"),
    ("не хочу", "не хочу/отказ"),
    ("спам", "раздражение от звонка"),
    ("надоели", "раздражение от звонка"),
    ("мне нельзя", "опасения"),
    ("боюсь", "опасения"),
    ("банкрот", "опасения по банкротству"),
    ("работа", "влияние на работу"),
    ("кто это", "не помнит звонок"),
    ("откуда у вас", "вопрос откуда данные"),
)

# Persona-fact slots surfaced inline in the summary. Anything else
# lives in the dedicated facts block — keeps the lead-in tight.
_HIGHLIGHT_SLOTS = {
    "total_debt": "сумма долга",
    "creditors": "кредиторы",
    "income": "доход",
    "family_status": "семья",
    "property_status": "имущество",
}


def _extract_promises(messages: list[dict]) -> list[str]:
    """Pull short manager-promise excerpts from prior call's messages.

    Returns up to 2 distinct promises in chronological order. Each
    excerpt is trimmed to 80 chars so a long monologue doesn't bloat
    the system prompt. Dedup on keyword family: «отправлю на почту»
    and «отправлю смету» count as one promise, not two.
    """
    found: list[str] = []
    seen: set[str] = set()
    for m in messages:
        if m.get("role") != "assistant":  # manager's side in our schema
            continue
        text = (m.get("content") or "").strip()
        if not text:
            continue
        low = text.lower()
        for kw in _PROMISE_PATTERNS:
            if kw in low:
                excerpt = text[:80].rstrip()
                key = kw.split()[0]
                if key in seen:
                    break
                seen.add(key)
                found.append(excerpt)
                if len(found) >= 2:
                    return found
                break
    return found


def _extract_objections(messages: list[dict]) -> list[str]:
    """Pull distinct client-objection categories from prior call.

    Returns up to 2 category labels (Russian, lowercase). Categories
    are stable across phrasing so the AI sees a clean signal.
    """
    found: list[str] = []
    seen: set[str] = set()
    for m in messages:
        if m.get("role") != "user":  # client side in our schema
            continue
        text = (m.get("content") or "").strip().lower()
        if not text:
            continue
        for needle, label in _OBJECTION_PATTERNS:
            if needle in text:
                if label in seen:
                    continue
                seen.add(label)
                found.append(label)
                if len(found) >= 2:
                    return found
    return found


def _persona_highlights(facts: dict) -> list[str]:
    """Render up to 3 high-value persona facts as «label: value» pairs."""
    out: list[str] = []
    for slot, label in _HIGHLIGHT_SLOTS.items():
        if slot not in facts:
            continue
        raw = facts[slot]
        value: str | None = None
        if isinstance(raw, str):
            value = raw
        elif isinstance(raw, dict):
            v = raw.get("value")
            if isinstance(v, (str, int, float)):
                value = str(v)
        if not value:
            continue
        out.append(f"{label}: {value}")
        if len(out) >= 3:
            break
    return out


def render_summary(
    *,
    completed_at: datetime | None,
    closing_emotion: str | None,
    score_total: float | None,
    terminal_outcome: str | None,
    judge_rationale: str | None,
    # PR-A.1 audit-fix params. All optional — older callers (and the
    # negative-cache path) keep working with a None set, producing
    # the legacy short summary.
    call_index: int | None = None,
    total_completed: int | None = None,
    messages: list[dict] | None = None,
    persona_facts: dict | None = None,
) -> str:
    """Build the Russian-language summary string.

    PR-A.1 enriched format:

        «Это уже 4-й звонок к этому клиенту (всего завершённых: 3).
         В прошлый звонок (вчера) клиент завершил на эмоции HOSTILE.
         Менеджер получил 42/100. Краткая причина окончания: бросил
         трубку. Клиент возражал по: цена/деньги, нужно посоветоваться.
         Менеджер обещал: «отправлю смету»; «перезвоню завтра».
         Известные факты: сумма долга: 1.2 млн.
         Судья отметил: грубый перебой клиента.»

    Trimmed to ``_MAX_SUMMARY_CHARS``.
    """
    age_label = _humanize_age(completed_at)
    parts: list[str] = []
    # Lead with the call counter so the AI immediately knows whether
    # this is a returning relationship or just a second contact.
    if call_index and call_index >= 2:
        parts.append(
            f"Это уже {call_index}-й звонок к этому клиенту "
            f"(всего завершённых: {total_completed or call_index - 1})."
        )
    emo = (closing_emotion or "cold").upper()
    parts.append(
        f"В прошлый звонок ({age_label}) клиент завершил на эмоции {emo}."
    )
    if score_total is not None:
        try:
            score_int = int(round(float(score_total)))
        except (TypeError, ValueError):
            score_int = None
        if score_int is not None:
            parts.append(f"Менеджер получил {score_int}/100.")
    parts.append(
        f"Краткая причина окончания: {_format_outcome(terminal_outcome)}."
    )

    # PR-A.1: extracted objections + promises. The substance the AI
    # needs to react contextually («вы обещали смету — где?»).
    if messages:
        try:
            objections = _extract_objections(messages)
            if objections:
                parts.append(
                    "Клиент возражал по: " + ", ".join(objections) + "."
                )
        except Exception:  # pragma: no cover — extractor must never crash render
            logger.debug("xsession: objection extraction failed", exc_info=True)
        try:
            promises = _extract_promises(messages)
            if promises:
                parts.append(
                    "Менеджер обещал: «" + "»; «".join(promises) + "»."
                )
        except Exception:  # pragma: no cover
            logger.debug("xsession: promise extraction failed", exc_info=True)

    # PR-A.1: persona facts inline — highest-value slots only.
    if persona_facts:
        try:
            highlights = _persona_highlights(persona_facts)
            if highlights:
                parts.append("Известные факты: " + "; ".join(highlights) + ".")
        except Exception:  # pragma: no cover
            logger.debug("xsession: persona highlights failed", exc_info=True)

    if judge_rationale:
        # Strip to a single sentence — the judge rationale is sometimes
        # a paragraph; we want one line so the system prompt stays lean.
        first_sentence = judge_rationale.strip().split("\n", 1)[0].split(". ", 1)[0]
        first_sentence = first_sentence.strip().rstrip(".")
        if first_sentence:
            parts.append(f"Судья отметил: {first_sentence}.")

    text = " ".join(parts).strip()
    if len(text) > _MAX_SUMMARY_CHARS:
        text = text[: _MAX_SUMMARY_CHARS - 1].rstrip() + "…"
    return text


# ── DB / Redis IO ───────────────────────────────────────────────────────


async def _load_prior_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    real_client_id: uuid.UUID,
    skip_session_id: uuid.UUID | None,
) -> TrainingSession | None:
    """Return the most-recent COMPLETED prior session, or None.

    Excludes ``skip_session_id`` so the in-flight session that triggered
    the lookup never matches itself.
    """
    stmt = (
        select(TrainingSession)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.real_client_id == real_client_id,
            TrainingSession.status == SessionStatus.completed,
        )
        .order_by(
            TrainingSession.ended_at.desc().nullslast(),
            TrainingSession.created_at.desc(),
        )
        .limit(1)
    )
    if skip_session_id is not None:
        stmt = stmt.where(TrainingSession.id != skip_session_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _judge_rationale(scoring_details: Any) -> str | None:
    """Pull the first useful judge sentence from ``scoring_details``.

    Tolerant of missing keys — returns None on anything unexpected.
    """
    if not isinstance(scoring_details, dict):
        return None
    judge = scoring_details.get("judge")
    if not isinstance(judge, dict):
        return None
    candidate = (
        judge.get("rationale_ru")
        or judge.get("rationale")
        or judge.get("verdict_ru")
        or judge.get("summary_ru")
    )
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    return None


async def fetch_last_session_summary(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    real_client_id: uuid.UUID,
    skip_session_id: uuid.UUID | None = None,
    redis_client: Any = None,
) -> str | None:
    """Return a 1-3 sentence Russian summary of the prior call, or None.

    Reads (in order):
      1. Redis cache at :func:`cache_key`. On hit, returns immediately.
      2. ``TrainingSession`` row for the most recent COMPLETED session
         matching ``(user_id, real_client_id)``, excluding
         ``skip_session_id``.
      3. Synthesizes the summary via :func:`render_summary` and writes
         it back to Redis with a 1h TTL.

    The Redis layer is opportunistic — when ``redis_client`` is None
    or unreachable, we fall through to the DB lookup. The summary is
    deterministic given the row, so a cache miss never produces a
    different answer than a cache hit.
    """
    # ── Cache lookup ────────────────────────────────────────────────
    key = cache_key(user_id, real_client_id)
    redis = redis_client
    if redis is None:
        try:
            from app.core.redis_pool import get_redis

            redis = get_redis()
        except Exception:  # pragma: no cover — pool not initialised in tests
            redis = None
    if redis is not None:
        try:
            cached = await redis.get(key)
        except Exception:
            cached = None
            logger.debug("xsession cache GET failed", exc_info=True)
        if cached:
            try:
                if isinstance(cached, bytes):
                    cached = cached.decode("utf-8")
                payload = json.loads(cached)
                if isinstance(payload, dict) and payload.get("v") == 1:
                    text = payload.get("summary")
                    if isinstance(text, str):
                        # Empty string is a tombstone meaning "we
                        # already checked and there is no prior".
                        return text or None
                elif isinstance(payload, str):
                    return payload or None
            except Exception:
                logger.debug("xsession cache payload malformed", exc_info=True)

    # ── DB read ─────────────────────────────────────────────────────
    prior = await _load_prior_session(
        db,
        user_id=user_id,
        real_client_id=real_client_id,
        skip_session_id=skip_session_id,
    )
    if prior is None:
        # Negative cache so a freshly-onboarded CRM client doesn't hit
        # the DB on every WS reconnect for the next hour.
        if redis is not None:
            try:
                await redis.set(
                    key,
                    json.dumps({"v": 1, "summary": ""}),
                    ex=_CACHE_TTL_SECONDS,
                )
            except Exception:
                logger.debug("xsession cache SET (miss) failed", exc_info=True)
        return None

    closing_emotion = extract_closing_emotion(prior.emotion_timeline)
    rationale = _judge_rationale(prior.scoring_details)

    # PR-A.1 (audit-fix): pull supplementary signal so the summary the
    # AI sees is substantive, not a one-liner. All three lookups are
    # opportunistic — if any throws we fall back to the legacy short
    # summary rather than 500 the caller. Total cost on cache miss =
    # three small SELECTs, gated behind the 1h Redis TTL.
    total_completed = 0
    try:
        from sqlalchemy import func as _sa_func
        cnt_stmt = select(_sa_func.count(TrainingSession.id)).where(
            TrainingSession.user_id == user_id,
            TrainingSession.real_client_id == real_client_id,
            TrainingSession.status == SessionStatus.completed,
        )
        total_completed = int((await db.execute(cnt_stmt)).scalar() or 0)
    except Exception:
        logger.debug("xsession: completed-count lookup failed", exc_info=True)

    transcript_msgs: list[dict] = []
    try:
        from app.models.training import Message
        msg_stmt = (
            select(Message.role, Message.content)
            .where(Message.session_id == prior.id)
            .order_by(Message.sequence_number.asc())
            .limit(40)  # last call rarely longer than 40 turns; cheap.
        )
        rows = (await db.execute(msg_stmt)).all()
        for r in rows:
            role_v = r[0].value if hasattr(r[0], "value") else str(r[0])
            transcript_msgs.append({"role": role_v, "content": r[1] or ""})
    except Exception:
        logger.debug("xsession: transcript fetch failed", exc_info=True)

    persona_facts: dict | None = None
    try:
        from app.services import persona_memory as _pm
        persona_row = await _pm.get_for_lead(db, lead_client_id=real_client_id)
        if persona_row is not None and persona_row.confirmed_facts:
            persona_facts = dict(persona_row.confirmed_facts)
    except Exception:
        logger.debug("xsession: persona facts lookup failed", exc_info=True)

    summary = render_summary(
        completed_at=prior.ended_at or prior.created_at,
        closing_emotion=closing_emotion,
        score_total=prior.score_total,
        terminal_outcome=prior.terminal_outcome,
        judge_rationale=rationale,
        # PR-A.1 enrichment params.
        call_index=total_completed + 1,
        total_completed=total_completed,
        messages=transcript_msgs,
        persona_facts=persona_facts,
    )

    if redis is not None:
        try:
            await redis.set(
                key,
                json.dumps({"v": 1, "summary": summary}),
                ex=_CACHE_TTL_SECONDS,
            )
        except Exception:
            logger.debug("xsession cache SET failed", exc_info=True)
    return summary


async def fetch_last_closing_emotion(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    real_client_id: uuid.UUID,
    skip_session_id: uuid.UUID | None = None,
) -> str | None:
    """Return ONLY the closing emotion of the prior session.

    Used by the WS bootstrap to decide whether to warm the emotion
    seed. Bypasses the summary cache because the seed decision is
    cheap and we don't want stale text-cache to outlive a row update.
    """
    prior = await _load_prior_session(
        db,
        user_id=user_id,
        real_client_id=real_client_id,
        skip_session_id=skip_session_id,
    )
    if prior is None:
        return None
    return extract_closing_emotion(prior.emotion_timeline)


async def evict_summary_cache(
    *,
    user_id: uuid.UUID | None,
    real_client_id: uuid.UUID | None,
    redis_client: Any = None,
) -> None:
    """Drop the cached summary for a (manager, real-client) pair.

    Called from :func:`completion_policy.finalize_training_session`
    so the next session-start sees the just-completed session in its
    summary, not the previous one.

    Silent on any failure — cache eviction is best-effort and must
    not fail the completion path.
    """
    if user_id is None or real_client_id is None:
        return
    redis = redis_client
    if redis is None:
        try:
            from app.core.redis_pool import get_redis

            redis = get_redis()
        except Exception:  # pragma: no cover
            return
    if redis is None:
        return
    try:
        await redis.delete(cache_key(user_id, real_client_id))
    except Exception:
        logger.debug(
            "xsession cache evict failed user=%s real_client=%s",
            user_id, real_client_id, exc_info=True,
        )


__all__ = [
    "WARMING_CLOSING_EMOTIONS",
    "cache_key",
    "evict_summary_cache",
    "extract_closing_emotion",
    "fetch_last_closing_emotion",
    "fetch_last_session_summary",
    "render_summary",
]
