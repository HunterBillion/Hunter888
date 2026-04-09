"use client";

import { motion } from "framer-motion";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Users,
  Phone,
  Target,
  BarChart3,
} from "lucide-react";
import type { GamePortfolioStats as Stats } from "@/types";

interface GamePortfolioStatsProps {
  stats: Stats | null;
  loading?: boolean;
  period: string;
  onPeriodChange: (period: string) => void;
}

const PERIOD_OPTIONS = [
  { value: "week", label: "Неделя" },
  { value: "month", label: "Месяц" },
  { value: "all", label: "Всё время" },
];

function TrendIcon({ direction }: { direction: string }) {
  if (direction === "up") return <TrendingUp size={12} style={{ color: "var(--success)" }} />;
  if (direction === "down") return <TrendingDown size={12} style={{ color: "var(--danger)" }} />;
  return <Minus size={12} style={{ color: "var(--text-muted)" }} />;
}

export function GamePortfolioStats({
  stats,
  loading,
  period,
  onPeriodChange,
}: GamePortfolioStatsProps) {
  if (loading || !stats) {
    return (
      <div
        className="rounded-xl p-4 animate-pulse"
        style={{ background: "var(--bg-secondary)", border: "1px solid var(--border-color)" }}
      >
        <div className="h-4 w-32 rounded skeleton-neon" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-16 rounded-lg skeleton-neon" />
          ))}
        </div>
      </div>
    );
  }

  const cards = [
    {
      label: "Историй",
      value: stats.total_stories,
      sub: `${stats.active} активных`,
      icon: Users,
      color: "var(--accent)",
    },
    {
      label: "Звонков",
      value: stats.total_calls,
      sub: `~${stats.avg_calls_per_story} / историю`,
      icon: Phone,
      color: "var(--success)",
    },
    {
      label: "Ср. балл",
      value: stats.avg_score,
      sub: stats.trend.direction === "up"
        ? `+${stats.trend.change_pct}%`
        : stats.trend.direction === "down"
          ? `${stats.trend.change_pct}%`
          : "стабильно",
      icon: Target,
      color: "var(--warning)",
    },
    {
      label: "Завершено",
      value: stats.completed,
      sub: stats.total_stories > 0
        ? `${Math.round((stats.completed / stats.total_stories) * 100)}%`
        : "0%",
      icon: BarChart3,
      color: "var(--success)",
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl p-4"
      style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border-color)",
      }}
    >
      {/* Header with period selector */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <BarChart3 size={14} style={{ color: "var(--accent)" }} />
          <span
            className="text-xs font-mono font-semibold uppercase tracking-wider"
            style={{ color: "var(--text-primary)" }}
          >
            Портфель
          </span>
          <TrendIcon direction={stats.trend.direction} />
        </div>

        <div className="flex gap-1">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onPeriodChange(opt.value)}
              className="text-xs font-mono px-2 py-1 rounded-md transition-colors"
              style={{
                background: period === opt.value ? "var(--accent)" : "var(--input-bg)",
                color: period === opt.value ? "var(--bg-primary)" : "var(--text-muted)",
                border: `1px solid ${period === opt.value ? "var(--accent)" : "var(--border-color)"}`,
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {cards.map((card, i) => (
          <motion.div
            key={card.label}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.05 }}
            className="rounded-lg p-3"
            style={{
              background: "var(--bg-primary)",
              border: "1px solid var(--border-color)",
            }}
          >
            <div className="flex items-center gap-1.5 mb-1">
              <card.icon size={11} style={{ color: card.color }} />
              <span
                className="text-xs font-mono"
                style={{ color: "var(--text-muted)" }}
              >
                {card.label}
              </span>
            </div>
            <div
              className="text-lg font-bold font-mono"
              style={{ color: "var(--text-primary)" }}
            >
              {card.value}
            </div>
            <div
              className="text-xs font-mono"
              style={{ color: "var(--text-muted)", opacity: 0.7 }}
            >
              {card.sub}
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}
