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
  const placementLeft = Math.max(0, 10 - r.placement_count);
  const streakIcon = r.current_streak > 0
    ? <TrendingUp size={14} style={{ color: "var(--neon-green)" }} />
    : r.current_streak < 0
    ? <TrendingDown size={14} style={{ color: "var(--neon-red)" }} />
    : <Minus size={14} style={{ color: "var(--text-muted)" }} />;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel overflow-hidden p-0"
    >
      <div
        className="p-6"
        style={{ background: "linear-gradient(135deg, rgba(255,215,0,0.14), rgba(59,130,246,0.08) 45%, rgba(0,0,0,0) 100%)" }}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.24em]" style={{ color: "var(--text-muted)" }}>
              Arena Rating
            </div>
            <div className="mt-2 flex items-end gap-3">
              <div className="font-display text-5xl font-black leading-none" style={{ color: "var(--text-primary)" }}>
                {Math.round(r.rating)}
              </div>
              <div className="pb-1 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                RD {Math.round(r.rd)}
              </div>
            </div>
            <div className="mt-3">
              <RankBadge tier={r.rank_tier} rating={r.rating} size="lg" />
            </div>
          </div>
          {!r.placement_done && (
            <div className="rounded-2xl px-4 py-3 text-right" style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <div className="font-mono text-[10px] uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                Калибровка
              </div>
              <div className="mt-1 text-2xl font-bold" style={{ color: "var(--accent)" }}>
                {r.placement_count}/10
              </div>
              <div className="mt-1 text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
                Осталось {placementLeft}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 p-6 md:grid-cols-4">
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
      <div className="flex items-center justify-between border-t px-6 py-4 font-mono text-[10px]" style={{ color: "var(--text-muted)", borderColor: "rgba(255,255,255,0.06)" }}>
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
