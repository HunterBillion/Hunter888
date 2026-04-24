"""Phase 0 hotfix tests — pilot-blocker regressions (Roadmap §5.2).

Covers H1 (update_preferences commit), H2 (PvP empty duel guard),
H4 (gender-aware archetype traits). H3/H5 are frontend — covered by
tsc/build. H6/H7 are flow wiring, covered by integration tests later.
"""

from __future__ import annotations

import ast
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent.parent


# ── H1 ────────────────────────────────────────────────────────────────────


def test_update_preferences_calls_commit_before_return():
    """The handler must ``await db.commit()`` before returning so a
    follow-up ``GET /me`` from another connection sees the new prefs.
    Prior to H1 it only did ``db.add(user)`` and exited.
    """
    users_py = APP_ROOT / "app" / "api" / "users.py"
    tree = ast.parse(users_py.read_text(encoding="utf-8"))

    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "update_preferences":
            target = node
            break
    assert target is not None, "update_preferences async function must exist"

    # Look for ``await db.commit()`` anywhere inside the function body.
    has_commit = any(
        isinstance(n, ast.Await)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and n.value.func.attr == "commit"
        for n in ast.walk(target)
    )
    assert has_commit, "update_preferences must await db.commit() before return"


def test_update_preferences_guards_team_integrity_error():
    """If two onboarding requests race on the same team name, we must
    catch the IntegrityError instead of bubbling a 500 to the user.
    """
    users_py = APP_ROOT / "app" / "api" / "users.py"
    source = users_py.read_text(encoding="utf-8")
    assert "IntegrityError" in source, (
        "users.py must import + handle IntegrityError in update_preferences"
    )


# ── H2 ────────────────────────────────────────────────────────────────────


def test_finalize_duel_short_circuits_on_empty_rounds():
    """Both rounds empty ⇒ duel cancelled without a judge call so no
    winner is falsely assigned. Also a ``pvp.duel_cancelled`` message is
    broadcast to each player so the UI doesn't celebrate nothing.
    """
    pvp_py = APP_ROOT / "app" / "ws" / "pvp.py"
    source = pvp_py.read_text(encoding="utf-8")
    assert "if not round1_messages and not round2_messages" in source, (
        "empty-rounds guard missing in _finalize_duel"
    )
    assert "DuelStatus.cancelled" in source, (
        "empty-rounds branch must set DuelStatus.cancelled"
    )
    assert "pvp.duel_cancelled" in source, (
        "empty-rounds branch must emit pvp.duel_cancelled WS event"
    )
    assert "no_round_data" in source, (
        "cancellation reason must carry no_round_data marker"
    )


# ── H4 ────────────────────────────────────────────────────────────────────


def test_trait_for_returns_male_female_neutral_variants():
    from app.services.between_call_narrator import _ARCHETYPE_TRAITS, trait_for

    for code, variants in _ARCHETYPE_TRAITS.items():
        assert set(variants.keys()) >= {"male", "female", "neutral"}, (
            f"{code} missing one of male/female/neutral"
        )
        male = trait_for(code, "male")
        female = trait_for(code, "female")
        neutral = trait_for(code, None)
        assert male and female and neutral
        # Neutral form should not grammatically commit to a gender
        # by starting with the bare masc/fem adjective stem alone;
        # easiest check is presence of the noun "клиент" which carries
        # masculine agreement but reads as generic "the client".
        assert "клиент" in neutral.lower() or "стыдится" in neutral.lower(), (
            f"{code} neutral variant must use a noun-phrase fallback"
        )


def test_trait_for_unknown_gender_uses_neutral():
    from app.services.between_call_narrator import trait_for

    assert trait_for("skeptic", "unknown") == trait_for("skeptic", None)
    assert trait_for("skeptic", "garbage") == trait_for("skeptic", None)


def test_trait_for_unknown_archetype_falls_back():
    from app.services.between_call_narrator import _NEUTRAL_FALLBACK, trait_for

    assert trait_for("definitely-not-an-archetype", "male") == _NEUTRAL_FALLBACK


def test_gamification_no_longer_defines_duplicate_archetype_dict():
    gamification_py = APP_ROOT / "app" / "api" / "gamification.py"
    source = gamification_py.read_text(encoding="utf-8")
    # The old inline dict had a signature line "archetype_traits = {"
    # The fix imports trait_for from between_call_narrator instead.
    assert "archetype_traits = {" not in source, (
        "gamification.py must no longer define its own archetype traits dict"
    )
    assert "from app.services.between_call_narrator import trait_for" in source, (
        "gamification.py must import trait_for from the canonical module"
    )


def test_narrator_context_has_gender_field():
    from app.services.between_call_narrator import NarratorContext

    ctx = NarratorContext()
    assert hasattr(ctx, "gender")
    assert ctx.gender == "unknown"
