"""Runtime finalizer (TZ-2 §10) — minimum-risk Phase 1 implementation.

The TZ-2 spec demands ONE canonical end-of-session helper that REST,
WS, silence-watchdog, and AI-farewell all converge on. A full single-
helper rewrite is high risk because the WS path is ~270 lines of inline
business effects (AI coach + RAG feedback + ManagerProgress + journey
snapshot + cleanup) that took the project months to converge on.

This module ships the SAFE incremental version:

* WS path stays as-is — it already produces the rich post-finalize
  enrichment (AI-coach report, RAG feedback, ManagerProgress XP,
  SessionHistory).
* REST path now calls ``apply_post_finalize_enrichment`` after its
  existing ``finalize_training_session`` policy stamp. Without this
  the user who ended a session via REST (call-page hangup, /end POST)
  loses XP, never gets the AI-coach report, and never feeds RAG.

Idempotency is enforced by ``SessionHistory.session_id UNIQUE`` —
the second writer hits IntegrityError on flush, the helper catches
it, returns the existing row, and skips re-emit / re-XP. So if WS
runs first (the usual case) and REST end is also triggered, REST is
a no-op for XP. If REST runs first and WS arrives later, same.

Phase 1B (next session) will fold the WS inline blocks into this
module so both callers literally execute the same code, dropping the
duplication. That refactor is intentionally NOT in this PR.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import SessionHistory
from app.models.training import TrainingSession

logger = logging.getLogger(__name__)


async def apply_post_finalize_enrichment(
    db: AsyncSession,
    *,
    session: TrainingSession,
    scores,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the post-finalize side-effects that the WS handler already runs.

    Steps (each best-effort, wrapped in try/except so the request never
    500s on an enrichment failure — the policy stamp + DomainEvent emit
    that the caller did before this function ran are the load-bearing
    parts):

      1. SessionHistory create (UNIQUE on session_id is the idempotency
         lock — second writer skips XP award).
      2. ``ManagerProgressService.update_after_session`` to award XP /
         level / skill points.
      3. AI-Coach ``generate_session_report`` to populate
         ``feedback_text`` / ``cited_moments`` / ``stage_analysis`` /
         ``historical_patterns``. Only if ``feedback_text`` is empty
         (don't overwrite a richer text the WS path already produced).
      4. RAG ``record_training_feedback`` if vector_checks present.

    ``state`` is the WS-style dict (call_outcome, archetype_code,
    base_difficulty, emotion_peak, had_comeback, scenario_code,
    scenario_name). REST callers pass ``None``; the helper synthesises
    defaults from the session row.

    Returns ``{"session_history_created": bool, "xp_earned": int|None,
    "coach_report_generated": bool, "rag_feedback_count": int}`` for
    test assertions and audit logging.
    """
    result: dict[str, Any] = {
        "session_history_created": False,
        "xp_earned": None,
        "coach_report_generated": False,
        "rag_feedback_count": 0,
    }

    if scores is None:
        return result

    state = state or {}
    user_id = session.user_id
    scoring_details = session.scoring_details or {}

    # ── Step 1+2: SessionHistory + XP award (idempotent via UNIQUE) ──
    sh = SessionHistory(
        user_id=user_id,
        session_id=session.id,
        scenario_code=state.get("scenario_code", "unknown"),
        archetype_code=state.get("archetype_code", "unknown"),
        difficulty=state.get("base_difficulty", 5),
        duration_seconds=session.duration_seconds or 0,
        score_total=int(scores.total or 0),
        outcome=state.get("call_outcome") or scoring_details.get("call_outcome") or "timeout",
        score_breakdown={
            "script_adherence": scores.script_adherence,
            "objection_handling": scores.objection_handling,
            "communication": scores.communication,
            "anti_patterns": scores.anti_patterns,
            "result": scores.result,
            "chain_traversal": getattr(scores, "chain_traversal", None),
            "trap_handling": getattr(scores, "trap_handling", None),
        },
        emotion_peak=state.get("emotion_peak", "cold"),
        traps_fell=(scoring_details.get("trap_handling") or {}).get("fell_count", 0),
        traps_dodged=(scoring_details.get("trap_handling") or {}).get("dodged_count", 0),
        chain_completed=bool(scoring_details.get("chain_completed")),
        had_comeback=bool(state.get("had_comeback")),
    )
    try:
        async with db.begin_nested():
            db.add(sh)
            await db.flush()
        result["session_history_created"] = True
    except IntegrityError:
        # WS path already created the SessionHistory + XP — skip our work
        # so we don't double-award. The existing row is the source of truth.
        existing = (
            await db.execute(
                select(SessionHistory).where(SessionHistory.session_id == session.id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            result["xp_earned"] = existing.xp_earned
            logger.info(
                "runtime_finalizer.skip_xp session=%s — SessionHistory already exists (xp=%s)",
                session.id, existing.xp_earned,
            )
        return result
    except Exception:
        logger.warning(
            "runtime_finalizer.session_history_failed session=%s",
            session.id, exc_info=True,
        )
        return result

    # XP award only runs when SessionHistory creation just succeeded.
    try:
        from app.services.manager_progress import ManagerProgressService
        svc = ManagerProgressService(db)
        mp_result = await svc.update_after_session(user_id, sh)
        sh.xp_earned = mp_result.get("xp_breakdown", {}).get("grand_total", 0)
        sh.xp_breakdown = mp_result.get("xp_breakdown", {})
        result["xp_earned"] = sh.xp_earned
    except Exception:
        logger.warning(
            "runtime_finalizer.xp_award_failed session=%s",
            session.id, exc_info=True,
        )

    # ── Step 3: AI-Coach report (only if feedback_text empty) ──
    if not session.feedback_text:
        try:
            from app.services.scenario_engine import generate_session_report, SessionConfig
            from app.services.session_manager import get_message_history, get_message_history_db

            messages = await get_message_history(session.id)
            if not messages:
                messages = await get_message_history_db(db, session.id)
            msg_list = [{"role": m["role"], "content": m["content"]} for m in messages]

            if msg_list:
                coach_report = await generate_session_report(
                    messages=msg_list,
                    config=SessionConfig(
                        scenario_code=state.get("scenario_code", "unknown"),
                        scenario_name=state.get("scenario_name", "Тренировка"),
                        template_id=uuid.uuid4(),
                        archetype=state.get("archetype_code", "skeptic"),
                        initial_emotion="cold",
                        client_awareness="low",
                        client_motivation="none",
                        difficulty=state.get("base_difficulty", 5),
                    ),
                    score_breakdown=scoring_details,
                    emotion_trajectory=session.emotion_timeline,
                )
                if coach_report.get("summary"):
                    parts: list[str] = []
                    parts.append(f"## Резюме\n{coach_report['summary']}")
                    if coach_report.get("strengths"):
                        parts.append("## Сильные стороны\n" + "\n".join(f"- {s}" for s in coach_report["strengths"]))
                    if coach_report.get("weaknesses"):
                        parts.append("## Слабые стороны\n" + "\n".join(f"- {w}" for w in coach_report["weaknesses"]))
                    if coach_report.get("recommendations"):
                        parts.append("## Рекомендации\n" + "\n".join(f"- {r}" for r in coach_report["recommendations"]))
                    session.feedback_text = "\n\n".join(parts)
                    result["coach_report_generated"] = True
        except Exception:
            logger.debug(
                "runtime_finalizer.coach_report_failed session=%s",
                session.id, exc_info=True,
            )

    # ── Step 4: RAG feedback ──
    try:
        from app.services.rag_feedback import record_training_feedback
        legal_data = scoring_details.get("legal_accuracy", {}) or {}
        vector_checks = ((legal_data.get("vector") or {}).get("vector_checks")) or []
        if vector_checks:
            validation_results = []
            for vc in vector_checks:
                chunk_id = vc.get("chunk_id")
                if not chunk_id:
                    continue
                is_error = vc.get("type") == "error"
                validation_results.append({
                    "chunk_id": chunk_id,
                    "accuracy": "incorrect" if is_error else "correct",
                    "manager_statement": (vc.get("fact", "") or "")[:200],
                    "score_delta": -2.0 if is_error else 0.5,
                    "explanation": vc.get("matched_error", ""),
                })
            if validation_results:
                count = await record_training_feedback(
                    db,
                    session_id=session.id,
                    user_id=user_id,
                    validation_results=validation_results,
                )
                result["rag_feedback_count"] = count or len(validation_results)
    except Exception:
        logger.debug(
            "runtime_finalizer.rag_feedback_failed session=%s",
            session.id, exc_info=True,
        )

    return result
