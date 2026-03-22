"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus, Swords, Flame } from "lucide-react";
import type { PvPRating } from "@/types";
import { RankBadge } from "./RankBadge";

interface Props {
  rating: PvPRating;
}

export function RatingCard({ rating: r }: Props) {
  const winRate = r.total_duels > 0 ? Math.round((r.wins / r.total_duels) * 100) : 0;
  const streakIcon = r.current_streak > 0
    ? <TrendingUp size={14} style={{ color: "var(--neon-green)" }} />
    : r.current_streak < 0
    ? <TrendingDown size={14} style={{ color: "var(--neon-red)" }} />
    : <Minus size={14} style={{ color: "var(--text-muted)" }} />;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel p-6"
    >
      <div className="flex items-center justify-between mb-4">
        <RankBadge tier={r.rank_tier} rating={r.rating} size="lg" />
        {!r.placement_done && (
          <span className="font-mono text-[10px] px-2 py-1 rounded-lg" style={{ background: "var(--accent-muted)", color: "var(--accent)" }}>
            Калибровка: {r.placement_count}/10
          </span>
        )}
      </div>

      <div className="grid grid-cols-4 gap-4 mt-4">
        <div className="text-center">
          <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Побед</div>
          <div className="font-display text-2xl font-bold" style={{ color: "var(--neon-green)" }}>{r.wins}</div>
        </div>
        <div className="text-center">
          <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Поражений</div>
          <div className="font-display text-2xl font-bold" style={{ color: "var(--neon-red)" }}>{r.losses}</div>
        </div>
        <div className="text-center">
          <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Win Rate</div>
          <div className="font-display text-2xl font-bold" style={{ color: "var(--accent)" }}>{winRate}%</div>
        </div>
        <div className="text-center">
          <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>Streak</div>
          <div className="font-display text-2xl font-bold flex items-center justify-center gap-1">
            {streakIcon}
            <span style={{ color: r.current_streak > 0 ? "var(--neon-green)" : r.current_streak < 0 ? "var(--neon-red)" : "var(--text-muted)" }}>
              {Math.abs(r.current_streak)}
            </span>
          </div>
        </div>
      </div>

      {/* Peak info */}
      <div className="mt-4 flex items-center justify-between font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
        <span className="flex items-center gap-1">
          <Flame size={10} style={{ color: "#FFD700" }} />
          Лучший streak: {r.best_streak}
        </span>
        <span className="flex items-center gap-1">
          <Swords size={10} />
          Всего дуэлей: {r.total_duels}
        </span>
        <span>Пик: {Math.round(r.peak_rating)}</span>
      </div>
    </motion.div>
  );
}
