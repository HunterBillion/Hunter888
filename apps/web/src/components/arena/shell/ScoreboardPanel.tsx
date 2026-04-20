"use client";

/**
 * ScoreboardPanel — left-column live leaderboard.
 *
 * Sprint 3 (2026-04-20). Single component shared across all 5 modes.
 * Handles three shapes:
 *   - Arena: 2-4 players ranked by score, crowns on top-3
 *   - Duel: just two rows (you vs opponent) with win/loss ticker
 *   - Rapid / PvE: single row (you) + ghosted "lap target"
 *
 * Any extra rich data (team, rating delta) is optional — mode pages
 * pass what they have.
 */

import { motion } from "framer-motion";
import { Bot, Crown, User } from "lucide-react";

export interface ScoreboardRow {
  userId: string;
  name: string;
  score: number;
  correct?: number;
  rank?: number;
  isBot?: boolean;
  isMe?: boolean;
  /** Optional rating delta since last snapshot — drives the ↑/↓ arrow. */
  delta?: number;
  /** True when disconnected / idle — greys the row. */
  disconnected?: boolean;
}

interface Props {
  rows: ScoreboardRow[];
  accentColor: string;
  /** Optional header label ("Арена", "Дуэль"). */
  title?: string;
}

export function ScoreboardPanel({ rows, accentColor, title = "Таблица" }: Props) {
  // Sort by score desc, place rank if not pre-set
  const sorted = [...rows].sort((a, b) => b.score - a.score);
  sorted.forEach((r, i) => {
    r.rank = r.rank ?? i + 1;
  });

  return (
    <div className="space-y-2">
      <div
        className="text-[10px] font-semibold uppercase tracking-wider"
        style={{ color: "var(--text-muted)" }}
      >
        {title}
      </div>

      {sorted.length === 0 && (
        <div
          className="rounded-xl px-3 py-4 text-center text-xs"
          style={{
            color: "var(--text-muted)",
            background: "var(--input-bg)",
            border: "1px solid var(--border-color)",
          }}
        >
          Нет игроков
        </div>
      )}

      {sorted.map((row) => (
        <motion.div
          key={row.userId}
          layout
          transition={{ duration: 0.35, ease: [0.2, 0.8, 0.3, 1] }}
          className="flex items-center gap-2 rounded-xl px-2.5 py-2"
          style={{
            background: row.isMe
              ? `${accentColor}14`
              : "var(--input-bg)",
            border: row.isMe
              ? `1px solid ${accentColor}55`
              : "1px solid var(--border-color)",
            opacity: row.disconnected ? 0.5 : 1,
          }}
        >
          {/* Rank + crown */}
          <div
            className="flex items-center justify-center w-5 shrink-0"
            style={{ color: rankColor(row.rank) }}
          >
            {row.rank && row.rank <= 3 ? (
              <Crown size={13} />
            ) : (
              <span className="text-xs font-mono font-bold">{row.rank}</span>
            )}
          </div>

          {/* Avatar */}
          <div
            className="flex h-7 w-7 items-center justify-center rounded-full shrink-0"
            style={{
              background: row.isMe ? accentColor : "var(--input-bg)",
              color: row.isMe ? "#0b0b14" : "var(--text-muted)",
              border: row.isMe ? "none" : "1px solid var(--border-color)",
            }}
          >
            {row.isBot ? <Bot size={13} /> : <User size={13} />}
          </div>

          {/* Name + correct count */}
          <div className="min-w-0 flex-1">
            <div
              className="text-sm font-semibold truncate"
              style={{ color: row.isMe ? accentColor : "var(--text-primary)" }}
            >
              {row.isMe ? "Ты" : row.name}
            </div>
            {typeof row.correct === "number" && (
              <div className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                {row.correct} верно
              </div>
            )}
          </div>

          {/* Score */}
          <div className="flex items-center gap-1">
            {typeof row.delta === "number" && row.delta !== 0 && (
              <span
                className="text-[10px] font-mono"
                style={{ color: row.delta > 0 ? "#22c55e" : "var(--danger)" }}
              >
                {row.delta > 0 ? "↑" : "↓"}
              </span>
            )}
            <span
              className="font-mono text-sm font-bold tabular-nums"
              style={{ color: row.isMe ? accentColor : "var(--text-primary)" }}
            >
              {row.score}
            </span>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

function rankColor(rank?: number): string {
  if (rank === 1) return "#facc15"; // gold
  if (rank === 2) return "#d1d5db"; // silver
  if (rank === 3) return "#f59e0b"; // bronze
  return "var(--text-muted)";
}
