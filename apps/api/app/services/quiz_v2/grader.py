"""quiz_v2.grader — deterministic answer matcher (Path A, A0 skeleton).

Owns the verdict layer of the v2 quiz pipeline. Replaces the legacy
LLM-streamed verdict in ``services/knowledge_quiz.evaluate_answer_streaming``
with a fast, deterministic match against a pre-computed answer key.

Strategies (first match wins):
  1. exact     — normalised string equality
  2. synonyms  — membership in pre-computed synonym list
  3. regex     — pattern from ``match_config.regex``
  4. keyword   — keyword AND/OR over normalised tokens
  5. embedding — cosine similarity ≥ threshold (default 0.85)

After every verdict, ``services.knowledge_quiz_validator_v2.validate_semantic``
runs as the LLM-second-opinion safety net (Q-NEW-1 decision: always fire,
not only on embedding). ``apply_upgrade`` is one-direction — never demotes
a deterministic-correct verdict.

Design doc: docs/QUIZ_V2_ARENA_DESIGN.md §7.
A0 contains the public surface only. A2 fills in the strategies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GradeResult:
    """Outcome of grading one user answer against an answer-key.

    Mirrors the on-the-wire ``quiz_v2.verdict.emitted`` payload (§5.1).
    """

    correct: bool
    score_delta: int
    expected_answer: str
    article_ref: str | None
    fast_path: str            # 'exact' | 'synonyms' | 'regex' | 'keyword' | 'embedding' | 'no_key' | 'validator_upgrade'
    strategy: str             # which strategy actually decided the verdict
    similarity: float | None  # populated for 'embedding' / 'validator_upgrade' paths
    degraded: bool = False    # true when validator_v2 swallowed an exception


async def grade_answer(
    *,
    answer_id: str,
    question_id: str,
    submitted_text: str,
    chunk_id: str,
    team_id: str | None,
) -> GradeResult:
    """Grade one user answer.

    A0 implementation: raises ``NotImplementedError``. A2 fills it in.
    Surface kept here so call-sites can import-and-typecheck against
    the final shape from day one.
    """

    raise NotImplementedError("quiz_v2.grader.grade_answer — A0 skeleton, A2 will implement")
