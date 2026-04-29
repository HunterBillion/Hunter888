"use client";

/**
 * ArenaBackground — пиксельный фон сцены дуэли по тиру игрока.
 *
 * 2026-04-29 (Фаза 3): пока без 8 PNG-тайлов (это Фаза 6). Дизайн строится
 * на CSS — два слоя: top-down accent radial в цвет тира и pixel-grid 23px.
 * Когда подъедут PNG-арты тиров, добавим 3-й слой с background-image
 * вместо grid (или поверх).
 *
 * Используется как обёртка вокруг сцены дуэли (FighterCard'ы + DuelChat).
 * Внутри opacity-30 + mix-blend-multiply, чтобы не мешало читать чат.
 */

import * as React from "react";
import { type PvPRankTier, PVP_RANK_COLORS, normalizeRankTier } from "@/types";

interface Props {
  tier?: PvPRankTier | string;
  /** Optional override for the radial intensity (0..1). Default 0.18. */
  intensity?: number;
  /** Tile pixel grid step (default 23). */
  gridStep?: number;
  /** Render children inside a relative container above the background. */
  children?: React.ReactNode;
  /** Additional className for the wrapper. */
  className?: string;
  style?: React.CSSProperties;
}

function tierColor(tier?: PvPRankTier | string): string {
  if (!tier) return "var(--accent)";
  const norm = normalizeRankTier(typeof tier === "string" ? tier : tier);
  return PVP_RANK_COLORS[norm] ?? "var(--accent)";
}

export function ArenaBackground({
  tier,
  intensity = 0.18,
  gridStep = 23,
  children,
  className = "",
  style,
}: Props) {
  const accent = tierColor(tier);
  const gridLine = `color-mix(in srgb, ${accent} 9%, transparent)`;
  const radialAlpha = Math.max(0, Math.min(1, intensity));
  return (
    <div
      className={`relative ${className}`}
      style={{
        background: "var(--bg-primary)",
        backgroundImage: [
          // 1. Top-down accent glow в цвет тира
          `radial-gradient(ellipse 80% 55% at 50% 0%, color-mix(in srgb, ${accent} ${Math.round(radialAlpha * 100)}%, transparent), transparent 65%)`,
          // 2. Тонкая пиксельная сетка
          `repeating-linear-gradient(0deg, transparent 0, transparent ${gridStep - 1}px, ${gridLine} ${gridStep - 1}px, ${gridLine} ${gridStep}px)`,
          `repeating-linear-gradient(90deg, transparent 0, transparent ${gridStep - 1}px, ${gridLine} ${gridStep - 1}px, ${gridLine} ${gridStep}px)`,
        ].join(", "),
        ...style,
      }}
    >
      {/* Декоративные «пылинки света» по краям — не мешают чтению, но дают глубину */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: [
            `radial-gradient(ellipse 60% 35% at 15% 25%, color-mix(in srgb, ${accent} 15%, transparent), transparent 70%)`,
            `radial-gradient(ellipse 50% 30% at 85% 75%, color-mix(in srgb, var(--magenta) 18%, transparent), transparent 70%)`,
          ].join(", "),
          mixBlendMode: "screen",
          opacity: 0.6,
        }}
      />
      {children}
    </div>
  );
}
