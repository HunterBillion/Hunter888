"""quiz_v2.rollout — feature-flag gate for the v2 grader (A0).

Single source of truth for "is the v2 pipeline active for this caller".
Honors both the master flag and the per-user whitelist so rollout can
proceed staged: author first, then 2-3 testers, then 50/50 A/B, then
100% (design doc §8 phase A6).

Lookup order:
  1. If ``user_id`` is in ``quiz_v2_grader_user_whitelist`` → ON
     (overrides the master flag — used for early author/tester access
     before the master flag flips)
  2. Else honor ``quiz_v2_grader_enabled`` master flag
"""

from __future__ import annotations

from app.config import settings


def is_quiz_v2_grader_enabled_for_user(user_id: str | None) -> bool:
    """Return True iff the v2 grader pipeline should run for this caller.

    ``user_id`` is the authenticated user's UUID as a string. Anonymous
    callers (``None``) honor the master flag only — never the whitelist.
    """

    if user_id is not None and user_id in settings.quiz_v2_grader_user_whitelist:
        return True
    return settings.quiz_v2_grader_enabled
