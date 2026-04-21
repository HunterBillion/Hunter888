"""Pure converters: activity result → Tournament Points (TP).

TP is separate from personal XP — XP grows level (long-term), TP is what you
earn each week and competes on the leaderboard. TP resets implicitly when
tournaments close and new weekly_sprint begins.

All functions are pure and unit-tested — no DB, no side effects.

Calibration notes:
    - Strong training session (score 80, difficulty 5) ≈ 74 TP
    - PvP win with +10 ELO ≈ 60 TP, loss ≈ 15 TP
    - Knowledge quiz with 100% accuracy + arena win ≈ 75 TP
    - Story mode full completion 5/5 with avg 70 ≈ 380 TP (large because 5 calls)
"""

from __future__ import annotations


def training_to_tp(score_total: float, difficulty: int) -> int:
    """Training session → TP.

    Formula: score * 0.8 + difficulty * 2, min 1.
    - score 0, diff 5  → 10 TP (floor — finishing is better than not finishing)
    - score 50, diff 5 → 50 TP
    - score 80, diff 5 → 74 TP
    - score 100, diff 10 → 100 TP (ceiling)
    """
    score = max(0.0, min(100.0, float(score_total or 0)))
    diff = max(1, min(10, int(difficulty or 5)))
    tp = round(score * 0.8 + diff * 2)
    return max(1, tp)


def pvp_to_tp(is_winner: bool, elo_delta: int, is_pve: bool) -> int:
    """PvP duel → TP.

    - Win: 50 base + min(20, max(0, elo_delta)) bonus.
    - Loss: 15 base (participation).
    - PvE multiplier: 0.5 (easier, worth less).
    """
    base = 50 if is_winner else 15
    bonus = max(0, min(20, int(elo_delta or 0))) if is_winner else 0
    multiplier = 0.5 if is_pve else 1.0
    tp = round((base + bonus) * multiplier)
    return max(1, tp)


def knowledge_to_tp(correct: int, total: int, arena_win: bool | None) -> int:
    """Knowledge quiz → TP.

    - Accuracy %: correct / total * 100.
    - Contribution: accuracy / 2 (so 100% accuracy → 50 TP).
    - Arena win bonus: +25.
    """
    correct = max(0, int(correct or 0))
    total = max(0, int(total or 0))
    if total == 0:
        return 0
    accuracy = (correct / total) * 100.0
    tp = accuracy / 2.0 + (25 if arena_win else 0)
    return max(1, round(tp))


def story_to_tp(avg_score: float, calls_completed: int, fully_completed: bool) -> int:
    """Story (multi-call) → TP.

    - avg_score * calls_completed (each call pulls its own weight).
    - +30 bonus for full 5/5 completion.
    """
    avg = max(0.0, min(100.0, float(avg_score or 0)))
    calls = max(0, int(calls_completed or 0))
    if calls == 0:
        return 0
    tp = avg * calls + (30 if fully_completed else 0)
    return max(1, round(tp))
