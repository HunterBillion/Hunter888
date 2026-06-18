"""A2 — quiz_v2.grader strategies + validator integration.

Locks in:
* Each of the 5 deterministic strategies returns the right verdict on
  representative inputs (plus a few adversarial ones).
* Strategy fall-through: declared strategy is tried first; on miss the
  remaining strategies run in order.
* validator_v2 upgrade (Q-NEW-1 (b) — always fires) can lift False→True
  but never demote True→False.
* validator_v2 exception is swallowed and surfaces as ``degraded=True``.
* No-key path returns a sane "incorrect, degraded" GradeResult.
* Embedding strategy degrades gracefully when the helper is unavailable.

We do NOT exercise the live embedding service here — that path is
hit-or-miss in CI. The unit tests use ``patch`` to drive both
``cosine_similarity`` and ``validate_semantic`` outcomes.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.services.quiz_v2.answer_keys import AnswerKey
from app.services.quiz_v2.grader import GradeResult, grade_answer


def _key(
    *,
    strategy: str = "exact",
    expected: str = "Да, через суд.",
    synonyms: list[str] | None = None,
    match_config: dict | None = None,
    flavor: str = "factoid",
    article_ref: str | None = "ст. 213.11",
) -> AnswerKey:
    return AnswerKey(
        id=str(uuid.uuid4()),
        chunk_id=str(uuid.uuid4()),
        team_id=None,
        question_hash="a" * 32,
        flavor=flavor,
        expected_answer=expected,
        match_strategy=strategy,
        match_config=match_config or {},
        synonyms=synonyms or [],
        article_ref=article_ref,
        knowledge_status="actual",
        is_active=True,
    )


# Avoid LLM noise — every test patches validator_v2 to a no-op pass-through
# so we can assert deterministic behavior independently. Tests that
# specifically exercise the upgrade path patch differently.
_PASSTHROUGH = AsyncMock(
    return_value=type(
        "Validation", (), {"equivalent": False, "partial": False, "score": 0.0, "missing": [], "reason": "", "skipped": True}
    )()
)


@pytest.fixture(autouse=True)
def _no_validator_upgrade(monkeypatch):
    """Default fixture: validator returns 'no upgrade' shape so grader's
    deterministic verdict shines through. Tests that need upgrade override."""
    async def _pass(question, correct_answer, manager_answer, rag_context=""):
        return type(
            "V", (), {
                "equivalent": False, "partial": False, "score": 0.0,
                "missing": [], "reason": "", "skipped": True,
            },
        )()

    def _no_upgrade(*, primary_is_correct, primary_score_delta, validation):
        return primary_is_correct, primary_score_delta, ""

    monkeypatch.setattr(
        "app.services.knowledge_quiz_validator_v2.validate_semantic",
        _pass,
    )
    monkeypatch.setattr(
        "app.services.knowledge_quiz_validator_v2.apply_upgrade",
        _no_upgrade,
    )


# ─── exact strategy ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_match():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Да, через суд.",
        key=_key(strategy="exact", expected="Да, через суд."),
    )
    assert result.correct is True
    assert result.fast_path == "exact"
    assert result.score_delta == 10


@pytest.mark.asyncio
async def test_exact_normalisation_handles_punctuation_case():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="ДА  через  суд",
        key=_key(strategy="exact", expected="Да, через суд."),
    )
    assert result.correct is True


@pytest.mark.asyncio
async def test_exact_miss_falls_through_no_match():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Совершенно не относится к теме",
        key=_key(strategy="exact", expected="Да, через суд."),
    )
    assert result.correct is False
    assert result.fast_path == "no_match"


# ─── synonyms strategy ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_synonyms_match_via_synonym_list():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="через судебный порядок",
        key=_key(
            strategy="synonyms",
            expected="через суд",
            synonyms=["судебный порядок", "в судебном порядке"],
        ),
    )
    assert result.correct is True
    assert result.fast_path == "synonyms"


@pytest.mark.asyncio
async def test_synonyms_containment_rescue():
    """User answer paraphrases; canonical is contained in submission."""
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Это решается через суд по заявлению должника",
        key=_key(strategy="synonyms", expected="через суд"),
    )
    assert result.correct is True


# ─── regex strategy ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regex_match():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Не позже 30 дней с момента уведомления",
        key=_key(
            strategy="regex",
            expected="30 дней",
            match_config={"regex": r"\b30\s*дн"},
        ),
    )
    assert result.correct is True
    assert result.fast_path == "regex"


@pytest.mark.asyncio
async def test_regex_invalid_pattern_does_not_crash():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="anything",
        key=_key(
            strategy="regex",
            expected="x",
            match_config={"regex": "[invalid("},
        ),
    )
    # Strategy returns False; grader falls through; final verdict no_match.
    assert result.correct is False
    assert result.fast_path == "no_match"


# ─── keyword strategy ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_keyword_all_mode_match():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Должник может списать долг через банкротство",
        key=_key(
            strategy="keyword",
            expected="банкротство списать долг",
            match_config={"keywords": ["банкротство", "долг"], "mode": "all"},
        ),
    )
    assert result.correct is True
    assert result.fast_path == "keyword"


@pytest.mark.asyncio
async def test_keyword_all_mode_partial_misses():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Только про банкротство",
        key=_key(
            strategy="keyword",
            expected="банкротство долг",
            match_config={"keywords": ["банкротство", "долг"], "mode": "all"},
        ),
    )
    assert result.correct is False


@pytest.mark.asyncio
async def test_keyword_any_mode_match():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Тут только долг",
        key=_key(
            strategy="keyword",
            expected="любой из ключей",
            match_config={"keywords": ["банкротство", "долг"], "mode": "any"},
        ),
    )
    assert result.correct is True


# ─── embedding strategy ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embedding_match_above_threshold():
    with patch(
        "app.services.quiz_v2.embedding_match.cosine_similarity",
        new=AsyncMock(return_value=0.92),
    ):
        result = await grade_answer(
            answer_id="aid", question_id="qid",
            submitted_text="Заёмщик может банкротиться при крупном долге",
            key=_key(
                strategy="embedding",
                expected="При долге > 500 тысяч возможно банкротство",
                match_config={"threshold": 0.85},
            ),
        )
    assert result.correct is True
    assert result.fast_path == "embedding"
    assert result.similarity == pytest.approx(0.92, rel=1e-3)


@pytest.mark.asyncio
async def test_embedding_below_threshold_falls_through():
    with patch(
        "app.services.quiz_v2.embedding_match.cosine_similarity",
        new=AsyncMock(return_value=0.5),
    ):
        result = await grade_answer(
            answer_id="aid", question_id="qid",
            submitted_text="совсем другая тема",
            key=_key(
                strategy="embedding",
                expected="При долге > 500 тысяч",
                match_config={"threshold": 0.85},
            ),
        )
    assert result.correct is False


@pytest.mark.asyncio
async def test_embedding_unavailable_returns_degraded():
    with patch(
        "app.services.quiz_v2.embedding_match.cosine_similarity",
        new=AsyncMock(return_value=None),
    ):
        result = await grade_answer(
            answer_id="aid", question_id="qid",
            submitted_text="some text",
            key=_key(strategy="embedding", expected="x"),
        )
    assert result.correct is False
    assert result.degraded is True


# ─── strategy fall-through ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_declared_exact_falls_through_to_synonyms():
    """Declared strategy misses; later strategy in order matches."""
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="через судебный порядок",
        key=_key(
            strategy="exact",  # exact will miss
            expected="через суд",
            synonyms=["судебный порядок"],  # synonyms will hit
        ),
    )
    assert result.correct is True
    assert result.fast_path == "synonyms"
    assert result.strategy == "synonyms"


# ─── validator_v2 upgrade path ───────────────────────────────────────


@pytest.mark.asyncio
async def test_validator_upgrade_lifts_false_to_true(monkeypatch):
    """Deterministic miss → validator says equivalent → upgrade to True."""

    async def _val(question, correct_answer, manager_answer, rag_context=""):
        return type(
            "V", (), {
                "equivalent": True, "partial": False, "score": 0.95,
                "missing": [], "reason": "semantic match", "skipped": False,
            },
        )()

    def _upgrade(*, primary_is_correct, primary_score_delta, validation):
        if not primary_is_correct and validation.equivalent:
            return True, 10, "upgraded"
        return primary_is_correct, primary_score_delta, ""

    monkeypatch.setattr(
        "app.services.knowledge_quiz_validator_v2.validate_semantic", _val
    )
    monkeypatch.setattr(
        "app.services.knowledge_quiz_validator_v2.apply_upgrade", _upgrade
    )

    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="что-то не похожее",
        key=_key(strategy="exact", expected="канонический ответ"),
    )
    assert result.correct is True
    assert result.fast_path == "validator_upgrade"
    assert result.similarity == pytest.approx(0.95, rel=1e-3)


@pytest.mark.asyncio
async def test_validator_cannot_demote_true(monkeypatch):
    """Deterministic match=True → validator must NOT change verdict to False."""

    async def _val(question, correct_answer, manager_answer, rag_context=""):
        return type(
            "V", (), {
                "equivalent": False, "partial": False, "score": 0.0,
                "missing": [], "reason": "validator disagreed", "skipped": False,
            },
        )()

    def _upgrade(*, primary_is_correct, primary_score_delta, validation):
        # Real apply_upgrade enforces: never demote a primary True.
        return primary_is_correct, primary_score_delta, ""

    monkeypatch.setattr(
        "app.services.knowledge_quiz_validator_v2.validate_semantic", _val
    )
    monkeypatch.setattr(
        "app.services.knowledge_quiz_validator_v2.apply_upgrade", _upgrade
    )

    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Да, через суд.",
        key=_key(strategy="exact", expected="Да, через суд."),
    )
    assert result.correct is True
    assert result.fast_path == "exact"


@pytest.mark.asyncio
async def test_validator_exception_marks_degraded(monkeypatch):
    """validator raises → grader swallows + sets degraded=True; deterministic verdict survives."""

    async def _boom(question, correct_answer, manager_answer, rag_context=""):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(
        "app.services.knowledge_quiz_validator_v2.validate_semantic", _boom
    )

    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="Да, через суд.",
        key=_key(strategy="exact", expected="Да, через суд."),
    )
    assert result.correct is True
    assert result.degraded is True


# ─── no-key path ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_key_returns_degraded_incorrect():
    result = await grade_answer(
        answer_id="aid", question_id="qid",
        submitted_text="anything",
        key=None,
    )
    assert isinstance(result, GradeResult)
    assert result.correct is False
    assert result.fast_path == "no_key"
    assert result.degraded is True
    assert result.score_delta == -2
