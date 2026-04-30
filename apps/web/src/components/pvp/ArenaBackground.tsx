"use client";

/**
 * ArenaBackground — пиксельный фон сцены дуэли по тиру игрока.
 *
 * 2026-04-29 (Фаза 3): начало — единый CSS-фон tier-color + pixel-grid.
 * 2026-04-30 (Фаза 6): 8 уникальных tier-биомов через композицию
 * background-image. PNG-тайлы не нужны — каждый биом строится на
 * radial/conic/repeating-linear градиентах, что эффективно бесплатно по
 * bundle size и легко тюнится через CSS-переменные.
 *
 * Биомы:
 *   iron        серо-коричневый камень с трещинами и тусклым факелом
 *   bronze      бронзовые колонны с тёплым отблеском
 *   silver      ледяной туман и кристаллики снега
 *   gold        золотая колоннада с лучом сверху
 *   platinum    аквамариновый хрусталь с бликами
 *   diamond     голубая геометрия + glitch-полосы
 *   master      пурпурная плазма с вращающимся ядром
 *   grandmaster вулкан — лава снизу + искры
 *   unranked    нейтральный pixel-grid (default)
 *
 * Используется как обёртка вокруг сцены дуэли (FighterCard + DuelChat).
 * Поверх лежит opacity-mask, чтобы фон не глушил читаемость чата.
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

function normTier(tier?: PvPRankTier | string): PvPRankTier {
  if (!tier) return "unranked";
  return normalizeRankTier(typeof tier === "string" ? tier : tier);
}

/**
 * tierBiomeLayers — возвращает массив CSS background-image слоёв (порядок
 * сверху вниз), уникальных для каждого тира. Каждый возврат — массив
 * строк, которые потом склеиваются через `, ` в один backgroundImage.
 *
 * Все цвета через color-mix var(--*), чтобы биом адаптировался под
 * light/dark theme автоматом.
 */
function tierBiomeLayers(tier: PvPRankTier, accent: string, gridStep: number): string[] {
  const grid = `color-mix(in srgb, ${accent} 9%, transparent)`;
  const baseGrid = [
    `repeating-linear-gradient(0deg, transparent 0, transparent ${gridStep - 1}px, ${grid} ${gridStep - 1}px, ${grid} ${gridStep}px)`,
    `repeating-linear-gradient(90deg, transparent 0, transparent ${gridStep - 1}px, ${grid} ${gridStep - 1}px, ${grid} ${gridStep}px)`,
  ];

  switch (tier) {
    case "iron": {
      // Тусклый факел сверху-слева + диагональные трещины.
      return [
        `radial-gradient(ellipse 50% 40% at 18% 12%, color-mix(in srgb, #ff7a3a 22%, transparent), transparent 65%)`,
        `radial-gradient(ellipse 70% 50% at 50% 100%, color-mix(in srgb, #2a1f15 65%, transparent), transparent 60%)`,
        // crack 1
        `linear-gradient(110deg, transparent 48%, color-mix(in srgb, ${accent} 18%, transparent) 48.5%, transparent 49%)`,
        // crack 2
        `linear-gradient(70deg, transparent 30%, color-mix(in srgb, ${accent} 14%, transparent) 30.4%, transparent 30.8%)`,
        ...baseGrid,
      ];
    }
    case "bronze": {
      // Вертикальные тёплые колонны.
      return [
        `radial-gradient(ellipse 60% 40% at 50% 0%, color-mix(in srgb, #c87a2c 28%, transparent), transparent 60%)`,
        `repeating-linear-gradient(90deg, transparent 0 90px, color-mix(in srgb, #c87a2c 11%, transparent) 90px 96px, transparent 96px 180px, color-mix(in srgb, #6a3818 14%, transparent) 180px 184px)`,
        ...baseGrid,
      ];
    }
    case "silver": {
      // Морозные кристаллы + холодный пар снизу.
      return [
        `radial-gradient(ellipse 100% 40% at 50% 0%, color-mix(in srgb, #a8d8e8 32%, transparent), transparent 60%)`,
        `radial-gradient(ellipse 70% 30% at 50% 100%, color-mix(in srgb, #6cabbc 30%, transparent), transparent 70%)`,
        // hexagon-like cells
        `conic-gradient(from 30deg at 25% 35%, color-mix(in srgb, #ffffff 14%, transparent) 0% 16%, transparent 16% 50%, color-mix(in srgb, #ffffff 8%, transparent) 50% 66%, transparent 66% 100%)`,
        ...baseGrid,
      ];
    }
    case "gold": {
      // Луч света сверху + золотая колоннада.
      return [
        `linear-gradient(180deg, color-mix(in srgb, #ffd166 28%, transparent) 0%, transparent 22%, transparent 70%, color-mix(in srgb, #4a2c10 50%, transparent) 100%)`,
        `radial-gradient(ellipse 12% 80% at 50% 50%, color-mix(in srgb, #fff2c8 32%, transparent), transparent 90%)`,
        `repeating-linear-gradient(90deg, transparent 0 100px, color-mix(in srgb, #d4a84b 16%, transparent) 100px 108px, transparent 108px)`,
        ...baseGrid,
      ];
    }
    case "platinum": {
      // Хрустальные грани + бликующие осколки.
      return [
        `radial-gradient(ellipse 60% 50% at 30% 20%, color-mix(in srgb, #5fe3e8 30%, transparent), transparent 65%)`,
        `radial-gradient(ellipse 50% 40% at 75% 70%, color-mix(in srgb, #aaf2f6 22%, transparent), transparent 60%)`,
        // diagonal crystal facets
        `repeating-linear-gradient(45deg, transparent 0 60px, color-mix(in srgb, #5fe3e8 10%, transparent) 60px 64px, transparent 64px 120px)`,
        `repeating-linear-gradient(-45deg, transparent 0 80px, color-mix(in srgb, #ffffff 7%, transparent) 80px 82px, transparent 82px)`,
        ...baseGrid,
      ];
    }
    case "diamond": {
      // Голубой неон + glitch-полосы.
      return [
        `radial-gradient(ellipse 80% 60% at 50% 30%, color-mix(in srgb, #5b9eff 32%, transparent), transparent 65%)`,
        // glitch horizontals (random-ish frequencies)
        `repeating-linear-gradient(0deg, transparent 0 17px, color-mix(in srgb, #5b9eff 18%, transparent) 17px 18px, transparent 18px 41px, color-mix(in srgb, #b380ff 14%, transparent) 41px 42px, transparent 42px 73px)`,
        // diamond facet hint
        `conic-gradient(from 0deg at 50% 50%, color-mix(in srgb, #5b9eff 10%, transparent) 0deg 30deg, transparent 30deg 90deg, color-mix(in srgb, #5b9eff 6%, transparent) 90deg 120deg, transparent 120deg 360deg)`,
        ...baseGrid,
      ];
    }
    case "master": {
      // Пурпурная плазма с вращающимся (статический в CSS) ядром.
      return [
        `radial-gradient(ellipse 80% 60% at 50% 50%, color-mix(in srgb, #d926d0 32%, transparent), transparent 60%)`,
        `radial-gradient(circle at 50% 50%, color-mix(in srgb, #ff5fa0 28%, transparent), transparent 25%)`,
        `conic-gradient(from 30deg at 50% 50%, transparent 0deg 60deg, color-mix(in srgb, #d926d0 14%, transparent) 60deg 120deg, transparent 120deg 240deg, color-mix(in srgb, #d926d0 14%, transparent) 240deg 300deg, transparent 300deg)`,
        ...baseGrid,
      ];
    }
    case "grandmaster": {
      // Вулкан: лава снизу, искры в воздухе, тёмный потолок.
      return [
        `radial-gradient(ellipse 90% 35% at 50% 100%, color-mix(in srgb, #ff5722 50%, transparent), transparent 70%)`,
        `radial-gradient(ellipse 40% 50% at 50% 75%, color-mix(in srgb, #ffae42 35%, transparent), transparent 70%)`,
        // sparks — small dots
        `radial-gradient(circle at 25% 65%, color-mix(in srgb, #ffd166 60%, transparent) 0 1.5px, transparent 2px)`,
        `radial-gradient(circle at 70% 50%, color-mix(in srgb, #ffae42 60%, transparent) 0 1.5px, transparent 2px)`,
        `radial-gradient(circle at 15% 30%, color-mix(in srgb, #ff8533 50%, transparent) 0 1.5px, transparent 2px)`,
        `radial-gradient(circle at 85% 25%, color-mix(in srgb, #ffd166 50%, transparent) 0 1.5px, transparent 2px)`,
        ...baseGrid,
      ];
    }
    case "unranked":
    default: {
      return [
        `radial-gradient(ellipse 80% 55% at 50% 0%, color-mix(in srgb, ${accent} 18%, transparent), transparent 65%)`,
        ...baseGrid,
      ];
    }
  }
}

export function ArenaBackground({
  tier,
  intensity = 0.18,
  gridStep = 23,
  children,
  className = "",
  style,
}: Props) {
  const tierKey = normTier(tier);
  const accent = tierColor(tier);
  const radialAlpha = Math.max(0, Math.min(1, intensity));
  const layers = tierBiomeLayers(tierKey, accent, gridStep);

  return (
    <div
      className={`relative ${className}`}
      data-tier-biome={tierKey}
      style={{
        background: "var(--bg-primary)",
        backgroundImage: layers.join(", "),
        ...style,
      }}
    >
      {/* Декоративный «пыл» поверх — даёт глубину, ограничен mix-blend-mode чтобы
          не глушить контент. radialAlpha управляет интенсивностью верхнего glow. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage: [
            `radial-gradient(ellipse 60% 35% at 15% 25%, color-mix(in srgb, ${accent} ${Math.round(radialAlpha * 100)}%, transparent), transparent 70%)`,
            `radial-gradient(ellipse 50% 30% at 85% 75%, color-mix(in srgb, var(--magenta) 18%, transparent), transparent 70%)`,
          ].join(", "),
          mixBlendMode: "screen",
          opacity: 0.55,
        }}
      />
      {children}
    </div>
  );
}
