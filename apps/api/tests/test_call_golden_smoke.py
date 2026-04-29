"""Sprint 0 §7 — golden_smoke metrics + grid dimensions.

The CLI itself drives real LLM calls (which we never run in CI), but
its pure helpers are unit-testable. These tests pin the metric formulas
and the grid shape so a future "let's add another archetype" change
doesn't silently double the LLM bill.
"""

from scripts.call_golden_smoke import (
    GOLDEN_ARCHETYPES,
    GOLDEN_MANAGER_LINES,
    TranscriptCell,
    _approx_tokens,
    _avg_inter_archetype_jaccard,
    _first_sentence_chars,
    _jaccard,
    _scan_ai_tells,
    _summarise,
)


def test_grid_dimensions_pinned():
    """Pin the grid size so a future contributor adding a 6th archetype
    or a 4th manager line has to update this number deliberately."""
    assert len(GOLDEN_ARCHETYPES) == 5
    assert len(GOLDEN_MANAGER_LINES) == 3
    # 5 × 3 × 2 flag states = 30 cells per run.


def test_grid_archetypes_unique():
    assert len(set(GOLDEN_ARCHETYPES)) == len(GOLDEN_ARCHETYPES)


def test_approx_tokens_uses_chars_div_two():
    assert _approx_tokens("") == 0
    assert _approx_tokens("hi") == 1  # 2 chars // 2
    assert _approx_tokens("Привет, мир!") == 6  # 12 chars // 2


def test_first_sentence_chars_until_punct():
    assert _first_sentence_chars("") == 0
    assert _first_sentence_chars("Алло.") == 5
    assert _first_sentence_chars("Алло. И что?") == 5
    assert _first_sentence_chars("без точки") == len("без точки")


def test_jaccard_basic():
    assert _jaccard(set(), set()) == 0.0
    assert _jaccard({"a"}, {"a"}) == 1.0
    assert _jaccard({"a", "b"}, {"a", "c"}) == 1 / 3


def test_scan_ai_tells_finds_seed():
    hits = _scan_ai_tells("Конечно, давайте разберёмся.")
    assert "конечно" in hits
    assert "давайте разберёмся" in hits


def test_scan_ai_tells_clean():
    assert _scan_ai_tells("Слушаю.") == []


def test_summarise_basic_shape():
    cells = [
        TranscriptCell(
            archetype="a", manager_line="line1", flag_state="off",
            reply="Конечно, понятно.", ai_tell_hits=["конечно", "понятно"],
            approx_tokens=10, first_sentence_chars=20,
        ),
        TranscriptCell(
            archetype="a", manager_line="line1", flag_state="on",
            reply="Слушаю.", ai_tell_hits=[],
            approx_tokens=4, first_sentence_chars=7,
        ),
    ]
    summary = _summarise(cells)
    assert summary["n_cells"] == 2
    assert "off" in summary and "on" in summary
    assert summary["off"]["ai_tells_per_reply_avg"] == 2.0
    assert summary["on"]["ai_tells_per_reply_avg"] == 0.0
    assert summary["off"]["ai_tell_hit_counts"] == {"конечно": 1, "понятно": 1}
    assert summary["on"]["ai_tell_hit_counts"] == {}


def test_inter_archetype_jaccard_lower_when_replies_diverge():
    """Two archetypes saying very different things → low Jaccard.
    Two archetypes saying the same thing → high Jaccard."""
    same_reply = [
        TranscriptCell(
            archetype="a", manager_line="L", flag_state="on",
            reply="алло слушаю да", ai_tell_hits=[],
            approx_tokens=10, first_sentence_chars=15,
        ),
        TranscriptCell(
            archetype="b", manager_line="L", flag_state="on",
            reply="алло слушаю да", ai_tell_hits=[],
            approx_tokens=10, first_sentence_chars=15,
        ),
    ]
    different_reply = [
        TranscriptCell(
            archetype="a", manager_line="L", flag_state="on",
            reply="алло слушаю", ai_tell_hits=[],
            approx_tokens=10, first_sentence_chars=15,
        ),
        TranscriptCell(
            archetype="b", manager_line="L", flag_state="on",
            reply="да говорите кто это", ai_tell_hits=[],
            approx_tokens=10, first_sentence_chars=15,
        ),
    ]
    high = _avg_inter_archetype_jaccard(same_reply, "on")
    low = _avg_inter_archetype_jaccard(different_reply, "on")
    assert high > low, (high, low)
    assert high == 1.0  # identical word sets


def test_inter_archetype_jaccard_zero_when_only_one_archetype_per_line():
    """Need at least 2 archetypes for a pairwise comparison; otherwise
    the metric is 0.0 (not raised), so the report can still print."""
    cells = [
        TranscriptCell(
            archetype="a", manager_line="L", flag_state="on",
            reply="hello", ai_tell_hits=[],
            approx_tokens=5, first_sentence_chars=5,
        ),
    ]
    assert _avg_inter_archetype_jaccard(cells, "on") == 0.0
