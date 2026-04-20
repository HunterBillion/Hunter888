"""QuizCase dataclass + hybrid CaseRouter.

Tiers of case generation:
  A. Seed kit (20 hardcoded JSON cases)  — 0ms, predictable, base
  B. Template fill-in (skeleton + LLM slots) — 1-2s, more variety (Этап 2)
  C. Pure LLM generation, cached per-user  — 3-8s, highest novelty (Этап 3)

Router picks tier based on:
  - user_level (experienced users get more variety)
  - mode (blitz ignores case entirely; themed/free_dialog use it)
  - difficulty target
  - cache pressure (Redis)

Этап 1 (2026-04-18) ships Tier A only. Tier B/C stubbed, routed-through with
graceful fallback.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

CaseComplexity = Literal["simple", "tangled", "adversarial"]


@dataclass
class QuizCase:
    """One narrative investigation — umbrella for 10-20 quiz questions."""

    case_id: str
    complexity: CaseComplexity
    debtor_name: str
    debtor_age: int
    debtor_occupation: str
    debt_amount: int
    creditors: list[str]
    trigger_event: str
    complicating_factors: list[str]
    narrative_hook: str

    # Map of StoryBeat → list of key legal hints for that beat. Generator
    # uses these as grounded seeds; LLM wraps them into question text.
    expected_beats: dict[str, list[str]] = field(default_factory=dict)

    # Runtime metadata (filled during session)
    source_tier: Literal["A", "B", "C"] = "A"

    def debt_amount_human(self) -> str:
        if self.debt_amount >= 1_000_000:
            return f"{self.debt_amount / 1_000_000:.1f}М ₽".replace(".0М", "М")
        return f"{self.debt_amount // 1000}к ₽"

    def creditors_summary(self) -> str:
        if len(self.creditors) <= 2:
            return ", ".join(self.creditors)
        return ", ".join(self.creditors[:2]) + f", ещё {len(self.creditors) - 2}"

    def to_redis_json(self) -> dict:
        """Serialize for SessionMemory storage."""
        return {
            "case_id": self.case_id,
            "complexity": self.complexity,
            "debtor_name": self.debtor_name,
            "debtor_age": self.debtor_age,
            "debtor_occupation": self.debtor_occupation,
            "debt_amount": self.debt_amount,
            "creditors": self.creditors,
            "trigger_event": self.trigger_event,
            "complicating_factors": self.complicating_factors,
            "narrative_hook": self.narrative_hook,
            "expected_beats": self.expected_beats,
            "source_tier": self.source_tier,
        }

    @classmethod
    def from_redis_json(cls, data: dict) -> "QuizCase":
        return cls(
            case_id=data["case_id"],
            complexity=data["complexity"],
            debtor_name=data["debtor_name"],
            debtor_age=data["debtor_age"],
            debtor_occupation=data["debtor_occupation"],
            debt_amount=data["debt_amount"],
            creditors=list(data["creditors"]),
            trigger_event=data["trigger_event"],
            complicating_factors=list(data.get("complicating_factors", [])),
            narrative_hook=data["narrative_hook"],
            expected_beats=dict(data.get("expected_beats", {})),
            source_tier=data.get("source_tier", "A"),
        )


_SEED_PATH = Path(__file__).resolve().parent / "cases_seed.json"
_SEED_CACHE: list[QuizCase] | None = None


def load_seed_cases(force_reload: bool = False) -> list[QuizCase]:
    """Load 20-case seed kit. Cached after first call."""
    global _SEED_CACHE
    if _SEED_CACHE is not None and not force_reload:
        return _SEED_CACHE
    try:
        raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
        cases = [QuizCase(source_tier="A", **c) for c in raw.get("cases", [])]
        _SEED_CACHE = cases
        logger.info("quiz_v2.cases: loaded %d seed cases", len(cases))
        return cases
    except Exception as exc:
        logger.error("quiz_v2.cases: failed to load seed JSON: %s", exc, exc_info=True)
        _SEED_CACHE = []
        return []


class CaseRouter:
    """Hybrid case router. Picks Tier A/B/C per session context.

    2026-04-18 (Этап 2/3): Tier B and C are now live. Distribution is
    (user_level-aware):

        lvl < 3   →  A 80% / B 20% / C 0%   (new users get predictable seed cases)
        lvl 3-9   →  A 40% / B 45% / C 15%  (veterans get variety)
        lvl ≥ 10  →  A 25% / B 45% / C 30%  (experts — most novelty)

    If a tier fails (LLM error, skeleton miss, Redis down) the router falls
    back to the next cheaper tier (C → B → A) so something always ships.
    """

    def __init__(self) -> None:
        self._seed: list[QuizCase] | None = None

    def _ensure_loaded(self) -> None:
        if self._seed is None:
            self._seed = load_seed_cases()

    async def pick_case(
        self,
        *,
        mode: str,
        difficulty: int,
        user_level: int = 1,
        user_id: str | None = None,
        exclude_case_ids: set[str] | None = None,
        preferred_complexity: CaseComplexity | None = None,
    ) -> QuizCase | None:
        """Route to Tier A/B/C with graceful fallback.

        Blitz mode returns None (blitz skips cases).
        """
        if mode == "blitz":
            return None

        self._ensure_loaded()
        seed = self._seed or []
        target_complexity: CaseComplexity = (
            preferred_complexity or self._difficulty_to_complexity(difficulty, user_level)
        )
        tier = self._pick_tier(user_level)

        # Feature-flag override: env can disable tiers B/C for safety
        from app.config import settings
        allow_b = bool(getattr(settings, "use_quiz_v2_tier_b", True))
        allow_c = bool(getattr(settings, "use_quiz_v2_tier_c", True))
        if tier == "C" and not allow_c:
            tier = "B" if allow_b else "A"
        if tier == "B" and not allow_b:
            tier = "A"

        logger.info(
            "quiz_v2.router: selected tier=%s complexity=%s (mode=%s diff=%d lvl=%d)",
            tier, target_complexity, mode, difficulty, user_level,
        )

        # ── Tier C: LLM gen with per-user cache ────────────────────────────
        if tier == "C" and user_id:
            try:
                from app.services.quiz_v2.tier_c import generate_tier_c_case
                case = await generate_tier_c_case(
                    user_id=user_id, complexity=target_complexity,
                )
                if case:
                    return case
                logger.info("quiz_v2.router: tier C returned None, falling back to B")
            except Exception as exc:
                logger.warning("quiz_v2.router: tier C exception, falling back: %s", exc)

        # ── Tier B: skeleton + LLM slot fill ───────────────────────────────
        if tier in ("B", "C"):
            try:
                from app.services.quiz_v2.tier_b import generate_tier_b_case
                case = await generate_tier_b_case(complexity=target_complexity)
                if case:
                    return case
                logger.info("quiz_v2.router: tier B returned None, falling back to A")
            except Exception as exc:
                logger.warning("quiz_v2.router: tier B exception, falling back: %s", exc)

        # ── Tier A: seed pool (always available) ───────────────────────────
        if not seed:
            logger.warning("quiz_v2.router: no seed cases — returning None")
            return None

        candidates = [
            c for c in seed
            if c.complexity == target_complexity
            and c.case_id not in (exclude_case_ids or set())
        ]
        if not candidates:
            candidates = [c for c in seed if c.case_id not in (exclude_case_ids or set())]
        if not candidates:
            candidates = seed
        chosen = random.choice(candidates)
        logger.info(
            "quiz_v2.router: tier=A case=%s complexity=%s",
            chosen.case_id, chosen.complexity,
        )
        return chosen

    @staticmethod
    def _pick_tier(user_level: int) -> Literal["A", "B", "C"]:
        """Weighted tier roll based on user level."""
        if user_level < 3:
            weights = [80, 20, 0]      # A, B, C
        elif user_level < 10:
            weights = [40, 45, 15]
        else:
            weights = [25, 45, 30]
        r = random.randint(1, 100)
        if r <= weights[0]:
            return "A"
        if r <= weights[0] + weights[1]:
            return "B"
        return "C"

    @staticmethod
    def _difficulty_to_complexity(difficulty: int, user_level: int) -> CaseComplexity:
        """Map (difficulty, user_level) → case complexity bucket.

        user_level gently pushes toward harder complexity for veterans:
          lvl < 5  → stay in simple/tangled
          lvl >= 5 → occasionally bump up
        """
        if difficulty <= 2:
            return "simple"
        if difficulty == 3:
            return "tangled" if user_level >= 5 else "simple"
        if difficulty == 4:
            return "tangled"
        return "adversarial"
