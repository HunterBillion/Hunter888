"""Sprint 0 §7 — call humanisation golden smoke.

Transcript-only A/B harness. NO TTS, NO WAV — keeps the runtime cheap
and reproducible so you can iterate without burning ElevenLabs quota or
waiting for audio to render.

What it does
  1. Generates a small fixed grid of (archetype × manager_line × turn)
     transcripts via generate_response.
  2. Runs the grid TWICE — once with CALL_HUMANIZED_V2=False (legacy
     baseline) and once with True (Sprint 0 path).
  3. Computes four lightweight metrics per transcript pair:
        * AI-tell hits  — count of KNOWN_RUSSIAN_AI_PHRASES substring
                          matches in the AI's reply.
        * Avg tokens    — len(reply) // 2 (Russian: ~2 chars per token).
        * Inter-archetype Jaccard — vocabulary overlap across archetypes
                          for the SAME manager line. Lower = more
                          differentiation, which is what we want.
        * First-sentence length — character count of the first sentence,
                          a rough proxy for "dictating-assistant" feel.
  4. Prints a side-by-side diff to stdout. Exit code 0 always (this is
     a developer smoke, not a CI gate).

Usage
  cd apps/api
  python -m scripts.call_golden_smoke

  # Or with a custom output JSON:
  python -m scripts.call_golden_smoke --out /tmp/smoke.json

Why it lives here and not in tests/
  Real LLM calls cost real money and wall-clock time. CI can't tolerate
  it. This script is for the human in the loop to read before flipping
  CALL_HUMANIZED_V2=true on a real environment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


# Five archetype codes drawn from the catalog. Pinned here (rather than
# loaded dynamically) so the smoke output is comparable across runs even
# if the catalog grows later.
GOLDEN_ARCHETYPES: tuple[str, ...] = (
    "skeptic",
    "pensioner_lonely",
    "young_aggressive",
    "executive_busy",
    "single_mother",
)

# Three manager openers covering different conversation pressures. The
# AI's reply to these is what we audit for AI-tells.
GOLDEN_MANAGER_LINES: tuple[str, ...] = (
    "Здравствуйте! Это Александр из юридического бюро. У вас есть минута поговорить про вашу задолженность?",
    "Я ведь не первый кто звонит — вы уже понимаете что без решения долг будет только расти?",
    "Слушайте, давайте начистоту: у вас есть план или нет?",
)


@dataclass
class TranscriptCell:
    archetype: str
    manager_line: str
    flag_state: str  # "off" or "on"
    reply: str
    ai_tell_hits: list[str]
    approx_tokens: int
    first_sentence_chars: int


@dataclass
class SmokeReport:
    cells: list[TranscriptCell]
    summary: dict[str, Any]


def _scan_ai_tells(text: str) -> list[str]:
    """Return the AI-tell phrases (lowercased) present in ``text``."""
    from app.services.ai_tell_scrubber import scan_sentence
    return list(scan_sentence(text))


def _approx_tokens(text: str) -> int:
    """Russian: ~2 chars per token."""
    return len(text) // 2


def _first_sentence_chars(text: str) -> int:
    """Length of the first sentence (up to first .!? or end)."""
    if not text:
        return 0
    for i, ch in enumerate(text):
        if ch in ".!?…":
            return i + 1
    return len(text)


def _jaccard(a: set[str], b: set[str]) -> float:
    """Word-level Jaccard. Used for inter-archetype differentiation."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _avg_inter_archetype_jaccard(
    cells: list[TranscriptCell], flag_state: str,
) -> float:
    """Average pairwise Jaccard across archetypes for the same manager
    line. Lower means archetypes speak more differently from each other —
    which is what humanisation V2 is supposed to encourage long-term.
    Sprint 0 doesn't ship voice fingerprints, so this is mostly a baseline
    capture for Sprint 1 to improve on.
    """
    by_line: dict[str, list[set[str]]] = {}
    for c in cells:
        if c.flag_state != flag_state:
            continue
        words = set(c.reply.lower().split())
        by_line.setdefault(c.manager_line, []).append(words)

    samples: list[float] = []
    for _, archetype_word_sets in by_line.items():
        if len(archetype_word_sets) < 2:
            continue
        for i in range(len(archetype_word_sets)):
            for j in range(i + 1, len(archetype_word_sets)):
                samples.append(_jaccard(
                    archetype_word_sets[i], archetype_word_sets[j],
                ))
    if not samples:
        return 0.0
    return sum(samples) / len(samples)


async def _generate_one(
    archetype: str, manager_line: str, *, flag_on: bool,
) -> str:
    """Run one LLM call. Toggles the V2 flag in-process before the call
    and restores it after, so the two passes don't bleed into each other.
    """
    from app.config import settings
    from app.services.llm import generate_response

    prev_flag = settings.call_humanized_v2
    settings.call_humanized_v2 = flag_on
    try:
        resp = await generate_response(
            system_prompt=(
                f"Ты — клиент-должник по архетипу '{archetype}'. "
                "Отвечай как реальный человек на телефонный звонок."
            ),
            messages=[{"role": "user", "content": manager_line}],
            emotion_state="cold",
            character_prompt_path=None,
            user_id="golden_smoke",
            scenario_prompt="",
            prefer_provider="auto",
            task_type="roleplay",
            session_mode="call",
        )
        return (resp.content or "").strip()
    finally:
        settings.call_humanized_v2 = prev_flag


async def _run_grid(*, flag_on: bool) -> list[TranscriptCell]:
    cells: list[TranscriptCell] = []
    flag_state = "on" if flag_on else "off"
    for archetype in GOLDEN_ARCHETYPES:
        for line in GOLDEN_MANAGER_LINES:
            try:
                reply = await _generate_one(archetype, line, flag_on=flag_on)
            except Exception as exc:
                reply = f"<ERROR: {exc}>"
            cells.append(TranscriptCell(
                archetype=archetype,
                manager_line=line,
                flag_state=flag_state,
                reply=reply,
                ai_tell_hits=_scan_ai_tells(reply),
                approx_tokens=_approx_tokens(reply),
                first_sentence_chars=_first_sentence_chars(reply),
            ))
    return cells


def _summarise(cells: list[TranscriptCell]) -> dict[str, Any]:
    on = [c for c in cells if c.flag_state == "on"]
    off = [c for c in cells if c.flag_state == "off"]

    def _avg(xs: list[int | float]) -> float:
        return (sum(xs) / len(xs)) if xs else 0.0

    return {
        "off": {
            "ai_tells_per_reply_avg": _avg([len(c.ai_tell_hits) for c in off]),
            "approx_tokens_avg": _avg([c.approx_tokens for c in off]),
            "first_sentence_chars_avg": _avg([c.first_sentence_chars for c in off]),
            "inter_archetype_jaccard": _avg_inter_archetype_jaccard(cells, "off"),
            "ai_tell_hit_counts": dict(Counter(
                tell for c in off for tell in c.ai_tell_hits
            )),
        },
        "on": {
            "ai_tells_per_reply_avg": _avg([len(c.ai_tell_hits) for c in on]),
            "approx_tokens_avg": _avg([c.approx_tokens for c in on]),
            "first_sentence_chars_avg": _avg([c.first_sentence_chars for c in on]),
            "inter_archetype_jaccard": _avg_inter_archetype_jaccard(cells, "on"),
            "ai_tell_hit_counts": dict(Counter(
                tell for c in on for tell in c.ai_tell_hits
            )),
        },
        "n_cells": len(cells),
    }


def _print_report(report: SmokeReport) -> None:
    s = report.summary
    print()
    print("=" * 70)
    print("Sprint 0 — call humanisation golden smoke")
    print("=" * 70)
    print(f"Cells: {s['n_cells']} ({len(GOLDEN_ARCHETYPES)} archetypes × "
          f"{len(GOLDEN_MANAGER_LINES)} lines × 2 flag states)")
    print()
    print(f"{'Metric':<40} {'OFF':>12} {'ON':>12}  Δ")
    print("-" * 70)
    for key, label in [
        ("ai_tells_per_reply_avg", "AI-tell hits per reply (avg)"),
        ("approx_tokens_avg", "Reply length (~tokens, avg)"),
        ("first_sentence_chars_avg", "First-sentence chars (avg)"),
        ("inter_archetype_jaccard", "Inter-archetype Jaccard"),
    ]:
        off = s["off"][key]
        on = s["on"][key]
        delta = on - off
        sign = "+" if delta >= 0 else ""
        print(f"{label:<40} {off:>12.2f} {on:>12.2f}  {sign}{delta:.2f}")
    print()
    if s["off"]["ai_tell_hit_counts"] or s["on"]["ai_tell_hit_counts"]:
        print("AI-tell phrase frequency:")
        all_phrases = sorted(set(
            list(s["off"]["ai_tell_hit_counts"]) + list(s["on"]["ai_tell_hit_counts"])
        ))
        for ph in all_phrases:
            off_n = s["off"]["ai_tell_hit_counts"].get(ph, 0)
            on_n = s["on"]["ai_tell_hit_counts"].get(ph, 0)
            print(f"  {ph!r:<35} OFF={off_n:>3}  ON={on_n:>3}")
        print()


async def _amain(out_path: Path | None) -> int:
    print("Running OFF pass (legacy baseline)…")
    cells_off = await _run_grid(flag_on=False)
    print("Running ON pass (CALL_HUMANIZED_V2=True)…")
    cells_on = await _run_grid(flag_on=True)
    cells = cells_off + cells_on
    report = SmokeReport(cells=cells, summary=_summarise(cells))
    _print_report(report)
    if out_path:
        out_path.write_text(
            json.dumps(
                {
                    "cells": [asdict(c) for c in cells],
                    "summary": report.summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        print(f"Full report → {out_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sprint 0 call humanisation A/B smoke (transcript-only, no TTS)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional JSON dump path (full transcripts + metrics).",
    )
    args = parser.parse_args()
    return asyncio.run(_amain(args.out))


if __name__ == "__main__":
    sys.exit(main())
