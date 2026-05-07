"""PR-7 tests: prove the 3 quiz examiner personalities are stronger now.

  - All examiner prompts include CITATION_INVARIANTS (anti-hallucination
    + cite-only-real-articles + admit-uncertainty + stay-in-FZ127).
  - Each examiner has its expected strictness (professor=normal,
    detective=strict, showman=lenient).
  - The strictness modifier text is appended to the prompt.
  - Roleplay personas (client, colleague) do NOT receive the invariants
    so they don't break in-character interactions.
  - get_personality() still resolves correctly (smoke).
"""

from __future__ import annotations


def test_examiner_personalities_carry_citation_invariants():
    from app.services.ai_personalities import AI_PERSONALITIES

    for name in ("professor", "detective", "showman"):
        cfg = AI_PERSONALITIES[name]
        assert "ИНВАРИАНТЫ" in cfg.system_prompt, name
        assert "БЕЗ ВЫДУМЫВАНИЯ ИСТОЧНИКОВ" in cfg.system_prompt, name
        assert "ПРИЗНАВАЙ НЕУВЕРЕННОСТЬ" in cfg.system_prompt, name
        assert "ОСТАВАЙСЯ ВНУТРИ ФЗ-127" in cfg.system_prompt, name


def test_per_archetype_strictness_levels():
    from app.services.ai_personalities import AI_PERSONALITIES

    assert AI_PERSONALITIES["professor"].strictness == "normal"
    assert AI_PERSONALITIES["detective"].strictness == "strict"
    assert AI_PERSONALITIES["showman"].strictness == "lenient"


def test_strictness_modifier_text_baked_in():
    from app.services.ai_personalities import AI_PERSONALITIES

    # Each archetype must include its own strictness section.
    assert "НОРМАЛЬНЫЙ" in AI_PERSONALITIES["professor"].system_prompt
    assert "ЖЁСТКИЙ" in AI_PERSONALITIES["detective"].system_prompt
    assert "МЯГКИЙ" in AI_PERSONALITIES["showman"].system_prompt


def test_roleplay_personas_dont_carry_examiner_invariants():
    """client/colleague are in-character actors, not legal examiners.

    Adding CITATION_INVARIANTS to them would force the roleplay client
    to talk like a juris­consult, breaking the simulation.
    """
    from app.services.ai_personalities import AI_PERSONALITIES

    for name in ("client", "colleague"):
        cfg = AI_PERSONALITIES[name]
        assert "ИНВАРИАНТЫ" not in cfg.system_prompt, name


def test_get_personality_smoke():
    from app.services.ai_personalities import get_personality

    # Forced mappings still hold
    assert get_personality("blitz").name == "showman"
    assert get_personality("rapid_blitz").name == "showman"
    assert get_personality("daily_challenge").name == "professor"

    # Themed defaults to detective when no preference
    assert get_personality("themed").name == "detective"

    # Free dialog defaults to professor when no preference
    assert get_personality("free_dialog").name == "professor"

    # Preference respected when compatible
    p = get_personality("free_dialog", preference="detective")
    assert p.name == "detective"


def test_prompt_length_grew_meaningfully():
    """Sanity: composed prompt is significantly bigger than the bare
    archetype text (otherwise the invariants didn't append)."""
    from app.services.ai_personalities import AI_PERSONALITIES

    for name in ("professor", "detective", "showman"):
        # Bare prompts are ~1500-2000 chars; composed ones must clear 2500.
        assert len(AI_PERSONALITIES[name].system_prompt) > 2500, name
