"use client";

/**
 * PixelMascot — пиксельный лев-маскот PvP-арены.
 *
 * Стилистически идентичен PixelAvatarSprites.ts / PixelIcon.tsx:
 * inline SVG из 256 `<rect>` с `image-rendering: pixelated`, без canvas,
 * без sprite-sheet PNG, без новых deps. Анимация — `setInterval` swap кадра.
 *
 * Состояния:
 *   idle    — спокойно сидит, мигает и иногда косит глаз (4 кадра loop)
 *   walk    — переход между якорями (2 кадра, лапы чередуются)
 *   cheer   — победа: лапы вверх, искры (1 кадр + jump через framer)
 *   sad     — поражение: голова вниз, слеза (1 кадр)
 *   sleep   — простой 30+ сек без событий (1 кадр + 'z')
 *
 * Контроль кадра:
 *   - state= "idle" | "walk" | ... — выбирает sprite-set
 *   - frame=N — фиксирует конкретный кадр (отключает auto-swap)
 *
 * Контроль рамки:
 *   - bordered — рисует пиксельную рамку с offset-shadow (как
 *     остальные pixel-карточки лобби)
 *   - frameColor — цвет рамки (default var(--accent))
 *
 * Цвет акцента (`g`-литерал в спрайтах):
 *   - accent — заменяет литерал `g` (default var(--accent))
 */

import { useEffect, useState, memo } from "react";
import { SPRITES, FRAME_INTERVAL_MS, PALETTE, type MascotState } from "./PixelMascotSprites";

export interface PixelMascotProps {
  /** Spr-state. Default `idle`. */
  state?: MascotState;
  /** Side в px. Default 64. */
  size?: number;
  /** Replace literal `g` with this CSS color. Default `var(--accent)`. */
  accent?: string;
  /** Manually pin to a specific frame index (disables auto-swap). */
  frame?: number;
  /** Wrap mascot in a chunky pixel-border (matches lobby card style). */
  bordered?: boolean;
  /** Border / shadow color. Default `var(--accent)`. */
  frameColor?: string;
  /** Background inside border (only used when `bordered`). */
  background?: string;
  className?: string;
  style?: React.CSSProperties;
  ariaLabel?: string;
}

function PixelMascotImpl({
  state = "idle",
  size = 64,
  accent = "var(--accent)",
  frame,
  bordered = false,
  frameColor = "var(--accent)",
  background = "transparent",
  className,
  style,
  ariaLabel = "Маскот арены",
}: PixelMascotProps) {
  const frames = SPRITES[state];
  const [frameIdx, setFrameIdx] = useState(0);

  useEffect(() => {
    if (typeof frame === "number") return; // manual pin → skip auto-swap
    setFrameIdx(0);
    if (frames.length <= 1 || FRAME_INTERVAL_MS[state] <= 0) return;
    const id = setInterval(() => {
      setFrameIdx((i) => (i + 1) % frames.length);
    }, FRAME_INTERVAL_MS[state]);
    return () => clearInterval(id);
  }, [state, frames.length, frame]);

  const idx = typeof frame === "number"
    ? Math.max(0, Math.min(frame, frames.length - 1))
    : frameIdx;
  const grid = frames[idx] ?? frames[0];

  const svg = (
    <svg
      role="img"
      aria-label={ariaLabel}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      shapeRendering="crispEdges"
      style={{ imageRendering: "pixelated", display: "block" }}
    >
      {grid.flatMap((row, y) =>
        row.split("").map((ch, x) => {
          if (ch === ".") return null;
          const fill = ch === "g" ? accent : PALETTE[ch];
          if (!fill) return null;
          return <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill={fill} />;
        })
      )}
    </svg>
  );

  if (!bordered) {
    return (
      <span className={className} style={{ display: "inline-block", ...style }}>
        {svg}
      </span>
    );
  }

  // pixel-frame: outline 2px + offset-shadow 3px (matches lobby cards).
  const pad = Math.max(4, Math.round(size * 0.08));
  return (
    <span
      className={className}
      style={{
        display: "inline-block",
        padding: pad,
        background,
        outline: `2px solid ${frameColor}`,
        outlineOffset: -2,
        boxShadow: `3px 3px 0 0 ${frameColor}`,
        borderRadius: 0,
        ...style,
      }}
    >
      {svg}
    </span>
  );
}

export const PixelMascot = memo(PixelMascotImpl);
