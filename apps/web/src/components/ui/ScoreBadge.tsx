"use client";

import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { scoreColor, scoreTier } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number | null;
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
  className?: string;
}

const ICON_MAP = {
  good: TrendingUp,
  mid: Minus,
  low: TrendingDown,
  none: Minus,
};

const SIZE_MAP = {
  sm: { text: "text-xs", icon: 10 },
  md: { text: "text-sm", icon: 12 },
  lg: { text: "text-2xl", icon: 16 },
};

/**
 * Accessible score display with color + icon indicator.
 * Ensures score meaning is conveyed even for color-blind users.
 */
export function ScoreBadge({ score, size = "md", showIcon = true, className = "" }: ScoreBadgeProps) {
  const color = scoreColor(score);
  const tier = scoreTier(score);
  const Icon = ICON_MAP[tier.icon];
  const s = SIZE_MAP[size];

  if (score === null || score === undefined) {
    return (
      <span className={`font-mono font-bold ${s.text} ${className}`} style={{ color }}>
        —
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 font-mono font-bold ${s.text} ${className}`}
      style={{ color }}
      title={`${Math.round(score)} — ${tier.label}`}
      aria-label={`Балл: ${Math.round(score)}, ${tier.label}`}
    >
      {showIcon && <Icon size={s.icon} />}
      {Math.round(score)}
    </span>
  );
}
