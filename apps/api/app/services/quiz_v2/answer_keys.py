"""quiz_v2.answer_keys — ORM access for ``quiz_v2_answer_keys`` (A0 skeleton).

Backs the deterministic grader by loading pre-computed answer keys for
a given ``(chunk_id, question_hash, team_id?)`` tuple. Lookup precedence
(Q-NEW-4 decision: global baseline + optional per-team override):

  1. Try ``(chunk_id, question_hash, team_id=<caller_team>)`` first
  2. Fall back to ``(chunk_id, question_hash, team_id=NULL)``

The table mirrors ``legal_knowledge_chunks`` columns (knowledge_status,
is_active, source, original_confidence) so the existing review-policy
state machine and review-queue UI can be reused without copy.

Design doc: docs/QUIZ_V2_ARENA_DESIGN.md §6.
A0 contains the public surface only. A1 ships the migration. A2 fills in
the loader using the shared async session.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def question_hash(question_text: str, canonical_answer: str) -> str:
    """Compute the stable identity hash for an answer-key row.

    Mirrors ``LegalKnowledgeChunk.content_hash`` shape:
    ``md5(question_text + "::" + canonical_answer)`` → 32-char hex.
    Idempotent upsert semantics for backfill and seed reloads.
    """

    payload = f"{question_text}::{canonical_answer}".encode("utf-8")
    return hashlib.md5(payload).hexdigest()


@dataclass(frozen=True)
class AnswerKey:
    """In-memory representation of a ``quiz_v2_answer_keys`` row.

    Fields mirror the SQL schema in design doc §6.
    """

    id: str
    chunk_id: str
    team_id: str | None
    question_hash: str
    flavor: str               # 'factoid' | 'strategic'
    expected_answer: str
    match_strategy: str       # 'exact' | 'synonyms' | 'regex' | 'keyword' | 'embedding'
    match_config: dict
    synonyms: list[str]
    article_ref: str | None
    knowledge_status: str
    is_active: bool


async def load_answer_key(
    *,
    chunk_id: str,
    question_hash: str,
    team_id: str | None,
) -> AnswerKey | None:
    """Load the active answer-key for a question, honoring team override.

    A0 implementation: raises ``NotImplementedError``. A2 fills in the
    actual SELECT using the shared async session.
    """

    raise NotImplementedError("quiz_v2.answer_keys.load_answer_key — A0 skeleton, A2 will implement")
