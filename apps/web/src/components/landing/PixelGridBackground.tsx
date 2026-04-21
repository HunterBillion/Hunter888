"use client";

import { useEffect, useRef } from "react";

/**
 * "Dead pixels" grid background.
 *
 * Renders a field of small FILLED squares (not outlines) arranged on a regular
 * grid — think of a CRT where each visible dot is a single pixel. At any
 * moment ~15% of these pixels are in a decay cycle: they fade out, go dark,
 * and fade back in on their own timeline. The rest stay lit.
 *
 * Key difference from an outline grid: the animation acts on the whole
 * square, not on its edges — when a pixel dies, the entire square vanishes.
 *
 * Five decay variants (all operate on the filled pixel itself):
 *   1. Quick blink  — short fade-out → dark → fade-in (~700ms)
 *   2. Slow fade    — long fade-out → long dark → long fade-in (~3s+)
 *   3. Stutter      — flickers 3–5 times before returning
 *   4. Cascade      — sharp death + slower return (~1.2s)
 *   5. Drift        — long dark period, ends at random (~4.5s)
 *
 * Respects prefers-reduced-motion: draws a static pixel field, skips RAF.
 */

type Variant = "quickBlink" | "slowFade" | "stutter" | "cascade" | "drift";

interface DecayCell {
  col: number;
  row: number;
  variant: Variant;
  startAt: number;
  duration: number;
  flickerCount: number;
}

const DEFAULT_CELL_SIZE = 24;
const DEFAULT_PIXEL_SIZE = 4;    // filled square size inside each cell
const ANIM_FRACTION = 0.15;

function pickVariant(rng: () => number): Variant {
  const n = Math.floor(rng() * 5);
  return (["quickBlink", "slowFade", "stutter", "cascade", "drift"] as const)[n];
}

function durationFor(variant: Variant, rng: () => number): number {
  switch (variant) {
    case "quickBlink": return 500 + rng() * 400;
    case "slowFade":   return 2700 + rng() * 1500;
    case "stutter":    return 1400 + rng() * 800;
    case "cascade":    return 900 + rng() * 600;
    case "drift":      return 3500 + rng() * 2000;
  }
}

/** 0 = fully lit, 1 = fully dark. */
function deathAt(variant: Variant, p: number, cell: DecayCell): number {
  switch (variant) {
    case "quickBlink":
      if (p < 0.3) return p / 0.3;
      if (p < 0.7) return 1;
      return 1 - (p - 0.7) / 0.3;
    case "slowFade":
      if (p < 0.2) return p / 0.2;
      if (p < 0.6) return 1;
      return 1 - (p - 0.6) / 0.4;
    case "stutter": {
      const flickers = cell.flickerCount;
      const flickerP = (p * flickers) % 1;
      if (flickerP < 0.35) return flickerP / 0.35;
      if (flickerP < 0.5) return 1;
      if (flickerP < 0.85) return 1 - (flickerP - 0.5) / 0.35;
      return 0;
    }
    case "cascade":
      if (p < 0.15) return p / 0.15;
      if (p < 0.55) return 1;
      return 1 - (p - 0.55) / 0.45;
    case "drift":
      if (p < 0.1) return p / 0.1;
      if (p < 0.8) return 1;
      return 1 - (p - 0.8) / 0.2;
  }
}

interface Props {
  /** Spacing between pixel centers in px. Default 24. */
  cellSize?: number;
  /** Size of the filled pixel square itself in px. Default 4. */
  pixelSize?: number;
  /** Base alpha of each lit pixel (0..1). Default 0.18. */
  pixelAlpha?: number;
}

export function PixelGridBackground({
  cellSize = DEFAULT_CELL_SIZE,
  pixelSize = DEFAULT_PIXEL_SIZE,
  pixelAlpha = 0.4,
}: Props = {}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Resolve --text-muted once; fall back to a neutral lavender.
    const rootStyle = getComputedStyle(document.documentElement);
    const raw = rootStyle.getPropertyValue("--text-muted").trim();
    const pixelColor = raw || "rgb(180, 170, 210)";

    let width = 0;
    let height = 0;
    let cols = 0;
    let rows = 0;
    let decayMap = new Map<number, DecayCell>(); // key = c*rows + r
    const rng = () => Math.random();

    const pixelOffset = (cellSize - pixelSize) / 2;

    const scheduleNextCycle = (cell: DecayCell, now: number) => {
      cell.variant = pickVariant(rng);
      cell.duration = durationFor(cell.variant, rng);
      // stagger: pixel stays lit a random quiet interval before next decay
      const quietGap = 800 + rng() * 6000;
      cell.startAt = now + quietGap;
      cell.flickerCount = 3 + Math.floor(rng() * 3);
    };

    const build = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      width = rect.width;
      height = rect.height;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      cols = Math.ceil(width / cellSize);
      rows = Math.ceil(height / cellSize);

      decayMap = new Map();
      const total = cols * rows;
      const animCount = Math.floor(total * ANIM_FRACTION);
      const used = new Set<number>();
      const now = performance.now();
      while (decayMap.size < animCount) {
        const idx = Math.floor(rng() * total);
        if (used.has(idx)) continue;
        used.add(idx);
        const col = idx % cols;
        const row = Math.floor(idx / cols);
        const variant = pickVariant(rng);
        const cell: DecayCell = {
          col,
          row,
          variant,
          startAt: now + rng() * 8000, // stagger first firings across 8s
          duration: durationFor(variant, rng),
          flickerCount: 3 + Math.floor(rng() * 3),
        };
        decayMap.set(col * rows + row, cell);
      }
    };

    /** Draw all STATIC pixels (once per build). */
    const drawStatic = () => {
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = pixelColor;
      ctx.globalAlpha = pixelAlpha;
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if (decayMap.has(c * rows + r)) continue;
          ctx.fillRect(c * cellSize + pixelOffset, r * cellSize + pixelOffset, pixelSize, pixelSize);
        }
      }
      ctx.globalAlpha = 1;
    };

    // Per frame: only repaint the animated subset.
    const frame = (now: number) => {
      ctx.fillStyle = pixelColor;

      for (const cell of decayMap.values()) {
        const x = cell.col * cellSize + pixelOffset;
        const y = cell.row * cellSize + pixelOffset;
        // Clear this pixel's footprint (+1px slack) so we never stack
        ctx.clearRect(x - 1, y - 1, pixelSize + 2, pixelSize + 2);

        if (now < cell.startAt) {
          // pre-firing idle — draw fully lit
          ctx.globalAlpha = pixelAlpha;
          ctx.fillRect(x, y, pixelSize, pixelSize);
          continue;
        }
        const p = (now - cell.startAt) / cell.duration;
        if (p >= 1) {
          scheduleNextCycle(cell, now);
          ctx.globalAlpha = pixelAlpha;
          ctx.fillRect(x, y, pixelSize, pixelSize);
          continue;
        }

        const d = deathAt(cell.variant, p, cell);
        const liveAlpha = (1 - d) * pixelAlpha;
        if (liveAlpha > 0.005) {
          ctx.globalAlpha = liveAlpha;
          ctx.fillRect(x, y, pixelSize, pixelSize);
        }
      }
      ctx.globalAlpha = 1;

      rafRef.current = requestAnimationFrame(frame);
    };

    const onResize = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      build();
      drawStatic();
      if (!reduced) rafRef.current = requestAnimationFrame(frame);
    };

    build();
    drawStatic();
    if (!reduced) rafRef.current = requestAnimationFrame(frame);
    window.addEventListener("resize", onResize);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", onResize);
    };
  }, [cellSize, pixelSize, pixelAlpha]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="absolute inset-0 w-full h-full pointer-events-none"
    />
  );
}
