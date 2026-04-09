"use client";

import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus, Swords, Flame, ChevronUp } from "lucide-react";
import type { PvPRating, PvPRankTier } from "@/types";
import { RankBadge } from "./RankBadge";

const TIER_THRESHOLDS: { tier: PvPRankTier; min: number }[] = [
  { tier: "grandmaster", min: 2900 },
  { tier: "master", min: 2600 },
  { tier: "diamond", min: 2300 },
  { tier: "platinum", min: 2000 },
  { tier: "gold", min: 1700 },
  { tier: "silver", min: 1400 },
  { tier: "bronze", min: 1000 },
  { tier: "iron", min: 0 },
];

/** Get division (III / II / I) within a tier based on position in range */
export function getDivision(rating: number, tier: PvPRankTier): string {
  if (tier === "grandmaster" || tier === "unranked") return "";
  const entry = TIER_THRESHOLDS.find((t) => t.tier === tier);
  const nextEntry = TIER_THRESHOLDS[TIER_THRESHOLDS.indexOf(entry!) - 1];
  if (!entry || !nextEntry) return "";
  const range = nextEntry.min - entry.min;
  const pos = (rating - entry.min) / range;
  if (pos < 1 / 3) return "III";
  if (pos < 2 / 3) return "II";
  return "I";
}

function getNextTier(rating: number, currentTier: PvPRankTier) {
  const idx = TIER_THRESHOLDS.findIndex((t) => t.tier === currentTier);
  if (idx <= 0) return null; // already grandmaster or not found
  const next = TIER_THRESHOLDS[idx - 1];
  const current = TIER_THRESHOLDS[idx];
  const range = next.min - current.min;
  const progress = Math.max(0, Math.min(1, (rating - current.min) / range));
  return { tier: next.tier, threshold: next.min, progress, pointsNeeded: Math.max(0, next.min - Math.round(rating)) };
}

interface Props {
  rating: PvPRating;
}

export function RatingCard({ rating: r }: Props) {
  const winRate = r.total_duels > 0 ? Math.round((r.wins / r.total_duels) * 100) : 0;
  const placementLeft = Math.max(0, 10 - r.placement_count);
  const nextTier = r.placement_done ? getNextTier(r.rating, r.rank_tier) : null;
  const streakIcon = r.current_streak > 0
    ? <TrendingUp size={14} style={{ color: "var(--success)" }} />
    : r.current_streak < 0
    ? <TrendingDown size={14} style={{ color: "var(--danger)" }} />
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
            <div className="font-mono text-sm tracking-[0.24em]" style={{ color: "var(--text-muted)" }}>
              Рейтинг арены
            </div>
            <div className="mt-2 flex items-end gap-3">
              <div className="font-display text-3xl sm:text-5xl font-black leading-none" style={{ color: "var(--text-primary)" }}>
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
              <div className="font-mono text-xs uppercase tracking-wider" style={{ color: "var(--text-muted)" }}>
                Калибровка
              </div>
              <div className="mt-1 text-2xl font-bold" style={{ color: "var(--accent)" }}>
                {r.placement_count}/10
              </div>
              <div className="mt-1 text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                Осталось {placementLeft}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 p-6 md:grid-cols-4">
        <div className="text-center">
          <div className="font-mono text-sm tracking-wider" style={{ color: "var(--text-muted)" }}>Побед</div>
          <div className="font-display text-2xl font-bold" style={{ color: "var(--success)" }}>{r.wins}</div>
        </div>
        <div className="text-center">
          <div className="font-mono text-sm tracking-wider" style={{ color: "var(--text-muted)" }}>Поражений</div>
          <div className="font-display text-2xl font-bold" style={{ color: "var(--danger)" }}>{r.losses}</div>
        </div>
        <div className="text-center">
          <div className="font-mono text-sm tracking-wider" style={{ color: "var(--text-muted)" }}>Процент побед</div>
          <div className="font-display text-2xl font-bold" style={{ color: "var(--accent)" }}>{winRate}%</div>
        </div>
        <div className="text-center">
          <div className="font-mono text-sm tracking-wider" style={{ color: "var(--text-muted)" }}>Серия</div>
          <div className="font-display text-2xl font-bold flex items-center justify-center gap-1">
            {streakIcon}
            <span style={{ color: r.current_streak > 0 ? "var(--success)" : r.current_streak < 0 ? "var(--danger)" : "var(--text-muted)" }}>
              {Math.abs(r.current_streak)}
            </span>
          </div>
        </div>
      </div>

      {/* Rank progress bar */}
      {nextTier && (
        <div className="px-6 py-4 border-t" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
              <ChevronUp size={12} className="inline" /> До следующего ранга
            </span>
            <span className="text-xs font-mono font-bold" style={{ color: "var(--accent)" }}>
              {nextTier.pointsNeeded} очков
            </span>
          </div>
          <div className="h-2 w-full rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
            <motion.div
              className="h-full rounded-full"
              style={{ background: "linear-gradient(90deg, var(--accent), var(--magenta))", boxShadow: "0 0 8px rgba(99,102,241,0.4)" }}
              initial={{ width: 0 }}
              animate={{ width: `${Math.round(nextTier.progress * 100)}%` }}
              transition={{ duration: 1, ease: "easeOut" }}
            />
          </div>
          <div className="flex items-center justify-between mt-1.5">
            <RankBadge tier={r.rank_tier} size="sm" />
            <RankBadge tier={nextTier.tier} size="sm" />
          </div>
        </div>
      )}

      {/* Peak info */}
      <div className="flex items-center justify-between border-t px-6 py-4 font-mono text-xs" style={{ color: "var(--text-muted)", borderColor: "rgba(255,255,255,0.06)" }}>
        <span className="flex items-center gap-1">
          <Flame size={13} style={{ color: "var(--streak-color)" }} />
          Лучший streak: {r.best_streak}
        </span>
        <span className="flex items-center gap-1">
          <Swords size={13} />
          Всего дуэлей: {r.total_duels}
        </span>
        <span>Пик: {Math.round(r.peak_rating)}</span>
      </div>
    </motion.div>
  );
}
