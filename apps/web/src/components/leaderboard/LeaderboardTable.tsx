"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { UserAvatar } from "@/components/ui/UserAvatar";

export interface LeaderboardRow {
  rank: number;
  user_id: string;
  full_name: string;
  avatar_url?: string | null;
  score: number;
  delta?: number | null;  // vs previous period
  subtitle?: string | null;  // e.g. "Level 5" or "120 TP · 3 wins"
  is_me?: boolean;
}

interface LeaderboardTableProps {
  rows: LeaderboardRow[];
  scoreUnit?: string;
  emptyMessage?: string;
}

function rankColor(rank: number): string {
  if (rank === 1) return "var(--rank-gold, #F7D154)";
  if (rank === 2) return "var(--rank-silver, #C8CDD3)";
  if (rank === 3) return "var(--rank-bronze, #C88A56)";
  return "var(--text-muted)";
}

export function LeaderboardTable({
  rows,
  scoreUnit = "TP",
  emptyMessage = "Пока нет данных",
}: LeaderboardTableProps) {
  if (!rows.length) {
    return (
      <div className="glass-panel p-8 text-center">
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {rows.map((row, i) => {
        const delta = row.delta ?? 0;
        const DeltaIcon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : Minus;
        const deltaColor = delta > 0
          ? "var(--success, #22c55e)"
          : delta < 0
            ? "var(--danger, #ef4444)"
            : "var(--text-muted)";

        return (
          <motion.div
            key={row.user_id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: Math.min(i * 0.02, 0.3) }}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors"
            style={{
              background: row.is_me
                ? "color-mix(in srgb, var(--accent) 12%, var(--input-bg))"
                : "var(--input-bg)",
              border: row.is_me
                ? "1px solid var(--accent)"
                : "1px solid var(--border-color)",
            }}
          >
            {/* Rank */}
            <div
              className="shrink-0 w-10 text-center font-mono font-bold tabular-nums"
              style={{
                color: rankColor(row.rank),
                fontSize: row.rank <= 3 ? "1.1rem" : "0.9rem",
              }}
            >
              {row.rank}
            </div>

            {/* Avatar + name */}
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <div
                className="shrink-0"
                style={{
                  outline: row.is_me ? "2px solid var(--accent)" : "1px solid var(--border-color)",
                  outlineOffset: row.is_me ? "1px" : "0",
                  borderRadius: "9999px",
                }}
              >
                <UserAvatar avatarUrl={row.avatar_url} fullName={row.full_name} size={32} />
              </div>
              <div className="min-w-0 flex-1">
                <div
                  className="text-sm font-medium truncate"
                  style={{ color: "var(--text-primary)" }}
                >
                  {row.full_name}
                  {row.is_me && (
                    <span
                      className="ml-2 text-[10px] font-mono uppercase tracking-wider"
                      style={{ color: "var(--accent)" }}
                    >
                      · Вы
                    </span>
                  )}
                </div>
                {row.subtitle && (
                  <div
                    className="text-[11px] truncate"
                    style={{ color: "var(--text-muted)" }}
                  >
                    {row.subtitle}
                  </div>
                )}
              </div>
            </div>

            {/* Delta */}
            {row.delta !== undefined && row.delta !== null && (
              <div
                className="shrink-0 flex items-center gap-1 text-[11px] font-mono tabular-nums"
                style={{ color: deltaColor }}
                title={`Изменение: ${delta > 0 ? "+" : ""}${delta}`}
              >
                <DeltaIcon size={11} />
                {delta !== 0 && <span>{delta > 0 ? "+" : ""}{delta}</span>}
              </div>
            )}

            {/* Score */}
            <div className="shrink-0 text-right">
              <div
                className="font-display font-bold tabular-nums"
                style={{ color: "var(--text-primary)", fontSize: "1rem" }}
              >
                {Math.round(row.score)}
              </div>
              <div
                className="text-[10px] font-mono uppercase tracking-wider"
                style={{ color: "var(--text-muted)" }}
              >
                {scoreUnit}
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
