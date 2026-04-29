"use client";

/**
 * HPBar — пиксельная шкала здоровья для FighterCard.
 *
 * 2026-04-29 (Фаза 3): сегментированный bar, каждый сегмент = пиксель-блок.
 * Цвет наполнения зависит от HP%:
 *   ≥70% — tier color (полный)
 *   30–70% — warning (жёлтый)
 *   <30% — danger (красный) + pulse
 *
 * value: 0..100. Анимация перехода через CSS transition (250ms ease-out).
 *
 * HP — НЕ из бэка. Это визуальная проекция: parent считает HP по
 * `judgeScore` или round wins и передаёт сюда. Компонент чисто
 * presentational.
 */

import * as React from "react";

interface Props {
  /** 0..100 */
  value: number;
  /** Tier-color для full state (CSS color). */
  tierColor: string;
  /** Direction: left-to-right (default) or right-to-left для зеркальной карточки. */
  direction?: "ltr" | "rtl";
  /** Сегментов в баре. По умолчанию 20. */
  segments?: number;
  /** Visual width в пикселях. */
  width?: number;
  /** Visual height. */
  height?: number;
}

export function HPBar({
  value,
  tierColor,
  direction = "ltr",
  segments = 20,
  width = 200,
  height = 14,
}: Props) {
  const clamped = Math.max(0, Math.min(100, value));
  const filled = Math.round((clamped / 100) * segments);

  // Color decision
  let color = tierColor;
  let pulsing = false;
  if (clamped < 30) {
    color = "var(--danger)";
    pulsing = true;
  } else if (clamped < 70) {
    color = "var(--warning)";
  }

  const segmentWidth = (width - segments + 1) / segments;
  const cells: React.ReactElement[] = [];
  for (let i = 0; i < segments; i += 1) {
    const idx = direction === "rtl" ? segments - 1 - i : i;
    const isFilled = idx < filled;
    cells.push(
      <span
        key={i}
        aria-hidden
        style={{
          width: segmentWidth,
          height,
          background: isFilled
            ? color
            : `color-mix(in srgb, ${color} 12%, transparent)`,
          boxShadow: isFilled ? `0 0 4px ${color}` : "none",
          transition: "background 220ms ease-out, box-shadow 220ms ease-out",
          animation: pulsing && isFilled ? "hp-pulse 1s ease-in-out infinite" : "none",
        }}
      />,
    );
  }

  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped)}
      aria-label="Здоровье бойца"
      className="relative inline-flex items-center"
      style={{
        width,
        height: height + 4,
        padding: 2,
        outline: "2px solid var(--text-primary)",
        outlineOffset: -2,
        background: "var(--bg-secondary)",
        boxShadow: "2px 2px 0 0 #000",
      }}
    >
      <div
        className="flex items-center"
        style={{
          width: width - 4,
          height,
          gap: 1,
          flexDirection: direction === "rtl" ? "row-reverse" : "row",
        }}
      >
        {cells}
      </div>
      {/* Внутренний CSS keyframe для пульсации (без global, scoped через name) */}
      <style>{`@keyframes hp-pulse { 0%,100% { opacity: 1 } 50% { opacity: 0.45 } }`}</style>
    </div>
  );
}
