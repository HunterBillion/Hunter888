"use client";

/**
 * RoundTransition — Kahoot-style "Leaderboard Moment" between rounds.
 *
 * Sprint 3 (2026-04-20). Full-screen overlay that:
 *   1. Shows the mini-scoreboard with animated rank shuffle.
 *   2. Counts down 3..2..1 to the next round.
 *   3. Auto-dismisses and fires the onFinish callback.
 *
 * Triggers the "round_end" → "round_start" SFX pair.
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { sfx } from "@/components/arena/sfx/useSFX";

interface Props {
  open: boolean;
  /** Label for the just-completed round ("Раунд 3"). */
  headline?: string;
  /** 2-4 top players for the mini-leaderboard preview. */
  leaderboard?: Array<{ name: string; score: number; isMe?: boolean }>;
  accentColor?: string;
  /** ms of countdown (default 3000 → 3..2..1). */
  countdownMs?: number;
  onFinish: () => void;
}

export function RoundTransition({
  open,
  headline = "Раунд завершён",
  leaderboard = [],
  accentColor = "#a78bfa",
  countdownMs = 3000,
  onFinish,
}: Props) {
  const [counter, setCounter] = useState(3);

  useEffect(() => {
    if (!open) return;
    sfx.play("round_end");
    setCounter(3);
    const step = Math.max(300, countdownMs / 3);
    const t1 = setTimeout(() => setCounter(2), step);
    const t2 = setTimeout(() => setCounter(1), step * 2);
    const t3 = setTimeout(() => {
      sfx.play("round_start");
      onFinish();
    }, step * 3);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, [open, countdownMs, onFinish]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[180] flex flex-col items-center justify-center"
          style={{ background: "rgba(6,6,14,0.92)" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            initial={{ scale: 0.8, y: -20 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ type: "spring", stiffness: 180, damping: 18 }}
            className="mb-6 text-center"
          >
            <div
              className="text-[11px] font-semibold uppercase tracking-widest mb-1"
              style={{ color: "var(--text-muted)" }}
            >
              Leaderboard Moment
            </div>
            <div
              className="font-display text-4xl md:text-5xl font-bold tracking-wide"
              style={{ color: accentColor }}
            >
              {headline}
            </div>
          </motion.div>

          {/* Mini leaderboard */}
          {leaderboard.length > 0 && (
            <div className="w-full max-w-md px-6 mb-8 space-y-2">
              {leaderboard.map((row, i) => (
                <motion.div
                  key={`${row.name}-${i}`}
                  layout
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.1 + i * 0.12 }}
                  className="flex items-center gap-3 rounded-xl px-4 py-2.5"
                  style={{
                    background: row.isMe
                      ? `${accentColor}22`
                      : "rgba(255,255,255,0.05)",
                    border: row.isMe
                      ? `1px solid ${accentColor}66`
                      : "1px solid rgba(255,255,255,0.08)",
                  }}
                >
                  <span
                    className="font-mono font-bold text-lg w-6"
                    style={{ color: rankColor(i + 1) }}
                  >
                    {i + 1}
                  </span>
                  <span
                    className="flex-1 text-base font-medium truncate"
                    style={{ color: row.isMe ? accentColor : "#fff" }}
                  >
                    {row.isMe ? "Ты" : row.name}
                  </span>
                  <span
                    className="font-mono font-bold tabular-nums"
                    style={{ color: row.isMe ? accentColor : "#fff" }}
                  >
                    {row.score}
                  </span>
                </motion.div>
              ))}
            </div>
          )}

          {/* Countdown big number */}
          <AnimatePresence mode="wait">
            <motion.div
              key={counter}
              initial={{ scale: 0.5, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 1.6, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.2, 0.8, 0.3, 1] }}
              className="font-display font-bold tabular-nums"
              style={{
                fontSize: 96,
                lineHeight: 1,
                color: accentColor,
                textShadow: `0 0 40px ${accentColor}66`,
              }}
            >
              {counter}
            </motion.div>
          </AnimatePresence>

          <div
            className="mt-4 text-sm uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Следующий раунд…
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function rankColor(rank: number): string {
  if (rank === 1) return "#facc15";
  if (rank === 2) return "#d1d5db";
  if (rank === 3) return "#f59e0b";
  return "rgba(255,255,255,0.6)";
}
