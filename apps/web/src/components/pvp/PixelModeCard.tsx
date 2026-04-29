"use client";

/**
 * PixelModeCard — единый формат карточки режима для лобби арены.
 *
 * 2026-04-29: создан в рамках унификации лобби (заменяет 3 разных inline-стиля
 * для PvP/PvE/Quiz карточек). Все варианты теперь на одной выкройке:
 *   - outline 2px tier-color, outline-offset -2px, radius 0
 *   - box-shadow 3px 3px 0 0 tier-color
 *   - hover: translate(-1, -1), shadow растёт до 4px (паттерн из DuelChat).
 *   - active: translate(2, 2), shadow исчезает.
 *   - locked: opacity 0.45, грей border, cursor not-allowed, шеврон pixel-lock.
 *
 * Проп `iconName` — ключ из PixelIcon. Цвет иконки = accent. Lock-индикатор
 * рендерится через тот же набор PixelIcon, без эмодзи.
 */

import * as React from "react";
import { motion } from "framer-motion";
import { PixelIcon, type PixelIconName } from "./PixelIcon";

interface Props {
  iconName: PixelIconName | string;
  name: string;
  desc?: string;
  /** CSS color (accent / success / warning) — рамка, тень, иконка. */
  accent: string;
  locked?: boolean;
  /** Min level — показывается рядом с иконкой замка. */
  lockLevel?: number;
  onClick?: () => void;
  /** When true, marks the card as currently selected. Подсветка фона + ▶ метка. */
  active?: boolean;
}

export function PixelModeCard({
  iconName,
  name,
  desc,
  accent,
  locked = false,
  lockLevel,
  onClick,
  active = false,
}: Props) {
  const borderColor = locked ? "var(--border-color)" : accent;
  const iconColor = locked ? "var(--text-muted)" : accent;

  return (
    <motion.button
      type="button"
      onClick={locked ? undefined : onClick}
      disabled={locked}
      whileHover={locked ? {} : { x: -1, y: -1 }}
      whileTap={locked ? {} : { x: 2, y: 2, transition: { duration: 0.05 } }}
      transition={{ type: "spring", stiffness: 600, damping: 30 }}
      className="relative p-3 text-left flex flex-col gap-2 w-full"
      style={{
        background: active
          ? `color-mix(in srgb, ${accent} 14%, var(--bg-panel))`
          : "var(--bg-panel)",
        outline: `2px solid ${borderColor}`,
        outlineOffset: -2,
        boxShadow: active
          ? `4px 4px 0 0 ${accent}, 0 0 12px color-mix(in srgb, ${accent} 35%, transparent)`
          : `3px 3px 0 0 ${borderColor}`,
        opacity: locked ? 0.55 : 1,
        cursor: locked ? "not-allowed" : "pointer",
        borderRadius: 0,
        transition: "background 120ms",
      }}
    >
      {/* Active marker */}
      {active && !locked && (
        <span
          aria-hidden
          className="absolute font-pixel"
          style={{
            top: 6,
            right: 8,
            color: accent,
            fontSize: 11,
            letterSpacing: "0.18em",
            textShadow: `0 0 6px ${accent}`,
          }}
        >
          ▶ OK
        </span>
      )}

      {/* Lock chip — top-right when locked */}
      {locked && (
        <span
          aria-hidden
          className="absolute inline-flex items-center gap-1 font-pixel"
          style={{
            top: 4,
            right: 6,
            padding: "2px 4px",
            background: "color-mix(in srgb, var(--warning) 12%, transparent)",
            border: "1px solid var(--warning)",
            color: "var(--warning)",
            fontSize: 10,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            borderRadius: 0,
          }}
        >
          <PixelIcon name="lock" size={10} color="var(--warning)" />
          {lockLevel != null && <span>LVL {lockLevel}</span>}
        </span>
      )}

      <PixelIcon name={iconName} size={28} color={iconColor} />

      <div
        className="font-pixel"
        style={{
          color: locked ? "var(--text-muted)" : "var(--text-primary)",
          fontSize: 14,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          lineHeight: 1.15,
        }}
      >
        {name}
      </div>
      {desc && (
        <div
          style={{
            color: "var(--text-muted)",
            fontSize: 12,
            lineHeight: 1.35,
          }}
        >
          {desc}
        </div>
      )}
    </motion.button>
  );
}
