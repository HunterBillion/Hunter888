"use client";

import { useRef, useEffect, useMemo, useCallback } from "react";

// ═══════════════════════════════════════════════════════════
//  PixelGridBackground — Animated pixel grid overlay
//  Canvas, position: fixed, z-index: 0, pointer-events: none
//  30fps throttle, dirty-cell rendering, visibility-aware
// ═══════════════════════════════════════════════════════════

const GRID = 24; // matches CSS grid in globals.css
const FPS = 30;
const FRAME_MS = 1000 / FPS;

// ── Scenario definitions ──────────────────────────────────

type Scenario = "PULSE" | "CASCADE" | "SPARKLE" | "COLOR_SHIFT" | "MATRIX_RAIN";

interface VariantConfig {
  scenarios: Scenario[];
  opacityRange: [number, number];
  animatedPct: number;
}

const VARIANTS: Record<string, VariantConfig> = {
  landing: {
    scenarios: ["PULSE", "SPARKLE"],
    opacityRange: [0.03, 0.12],
    animatedPct: 0.15,
  },
  leaderboard: {
    scenarios: ["MATRIX_RAIN"],
    opacityRange: [0.04, 0.08],
    animatedPct: 0.10,
  },
  pvp: {
    scenarios: ["CASCADE", "COLOR_SHIFT"],
    opacityRange: [0.05, 0.10],
    animatedPct: 0.15,
  },
  platform: {
    scenarios: ["PULSE"],
    opacityRange: [0.02, 0.04],
    animatedPct: 0.08,
  },
};

// ── Color palette (CSS var fallbacks) ─────────────────────

const PAL = {
  accent: "#6b4dc7",
  accentHover: "#7c5dd6",
  brandDeep: "#311573",
  success: "#28c840",
  white: "#e8e4f0",
};

// ── Cell state ────────────────────────────────────────────

interface Cell {
  col: number;
  row: number;
  scenario: Scenario;
  phase: number;       // 0..1 current animation progress
  duration: number;    // total cycle duration (seconds)
  delay: number;       // initial delay before start
  active: boolean;
  opacity: number;     // current computed opacity
  prevOpacity: number; // last rendered opacity (dirty check)
  color: string;
}

// ── Animation functions ───────────────────────────────────

function animatePulse(cell: Cell, _t: number): void {
  const p = ((cell.phase % 1) + 1) % 1;
  cell.opacity = Math.sin(p * Math.PI) * 0.12;
  cell.color = PAL.accent;
}

function animateCascade(cell: Cell, t: number): void {
  const waveY = ((t * 100 / (cell.duration * 400)) % 1); // 0..1 sweep
  const cellY = cell.row / 100; // normalized
  const dist = Math.abs(cellY - waveY);
  const width = 0.03; // 3 rows width
  cell.opacity = dist < width ? (1 - dist / width) * 0.10 : 0;
  cell.color = PAL.accent;
}

function animateSparkle(cell: Cell, _t: number): void {
  const p = cell.phase % 1;
  if (p < 0.05) {
    // Flash
    cell.opacity = (1 - p / 0.05) * 0.15;
    cell.color = p < 0.02 ? PAL.white : PAL.accent;
  } else {
    cell.opacity = 0;
  }
}

function animateColorShift(cell: Cell, _t: number): void {
  const p = cell.phase % 1;
  const colors = [PAL.accent, PAL.accentHover, PAL.brandDeep, PAL.accent];
  const idx = Math.floor(p * (colors.length - 1));
  cell.color = colors[Math.min(idx, colors.length - 1)];
  cell.opacity = 0.06 + Math.sin(p * Math.PI) * 0.04;
}

function animateMatrixRain(cell: Cell, _t: number): void {
  const p = cell.phase % 1;
  // Column drops: cells light up based on row position in phase
  const targetRow = Math.floor(p * 40);
  const dist = Math.abs(cell.row - targetRow);
  if (dist < 3) {
    cell.opacity = (1 - dist / 3) * 0.08;
    cell.color = dist === 0 ? PAL.success : PAL.accent;
  } else {
    cell.opacity = 0;
  }
}

const ANIMATORS: Record<Scenario, (cell: Cell, t: number) => void> = {
  PULSE: animatePulse,
  CASCADE: animateCascade,
  SPARKLE: animateSparkle,
  COLOR_SHIFT: animateColorShift,
  MATRIX_RAIN: animateMatrixRain,
};

// ── Component ─────────────────────────────────────────────

interface Props {
  variant?: keyof typeof VARIANTS;
}

export function PixelGridBackground({ variant = "platform" }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const cellsRef = useRef<Cell[]>([]);
  const rafRef = useRef(0);
  const lastFrameRef = useRef(0);
  const sizeRef = useRef({ w: 0, h: 0, cols: 0, rows: 0 });

  const config = useMemo(() => VARIANTS[variant] || VARIANTS.platform, [variant]);

  // Mobile detection — reduce animated cells
  const isMobile = useMemo(() => {
    if (typeof window === "undefined") return false;
    return window.innerWidth < 768 || /Android|iPhone|iPad/i.test(navigator.userAgent);
  }, []);

  const animPct = isMobile ? config.animatedPct * 0.5 : config.animatedPct;

  // Init cells for current canvas size
  const initCells = useCallback((cols: number, rows: number) => {
    const total = cols * rows;
    const animated = Math.floor(total * animPct);
    const cells: Cell[] = [];

    // Pick random cells to animate
    const indices = new Set<number>();
    while (indices.size < animated) {
      indices.add(Math.floor(Math.random() * total));
    }

    for (const idx of indices) {
      const col = idx % cols;
      const row = Math.floor(idx / cols);
      const scenario = config.scenarios[Math.floor(Math.random() * config.scenarios.length)];

      let duration: number;
      switch (scenario) {
        case "PULSE": duration = 2 + Math.random() * 2; break;
        case "CASCADE": duration = 8; break;
        case "SPARKLE": duration = 0.15 + Math.random() * 0.15; break;
        case "COLOR_SHIFT": duration = 5 + Math.random() * 2; break;
        case "MATRIX_RAIN": duration = 3 + Math.random() * 2; break;
      }

      cells.push({
        col, row, scenario,
        phase: 0,
        duration,
        delay: Math.random() * duration,
        active: true,
        opacity: 0,
        prevOpacity: -1, // force first draw
        color: PAL.accent,
      });
    }

    cellsRef.current = cells;
  }, [config.scenarios, animPct]);

  // Resize handler
  const resize = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const w = window.innerWidth;
    const h = window.innerHeight;
    canvas.width = w;
    canvas.height = h;
    const cols = Math.ceil(w / GRID);
    const rows = Math.ceil(h / GRID);
    sizeRef.current = { w, h, cols, rows };
    initCells(cols, rows);

    // Full clear
    const ctx = ctxRef.current;
    if (ctx) ctx.clearRect(0, 0, w, h);
  }, [initCells]);

  // Animation loop — 30fps throttled, dirty-cell only
  const animate = useCallback((now: number) => {
    rafRef.current = requestAnimationFrame(animate);

    // Throttle to 30fps
    if (now - lastFrameRef.current < FRAME_MS) return;
    const dt = (now - lastFrameRef.current) / 1000;
    lastFrameRef.current = now;

    const ctx = ctxRef.current;
    if (!ctx) return;

    const cells = cellsRef.current;
    const t = now / 1000;

    for (const cell of cells) {
      // Advance phase
      cell.phase = ((t - cell.delay) / cell.duration);

      // Sparkle: re-trigger randomly (Poisson ~1/sec)
      if (cell.scenario === "SPARKLE" && cell.opacity === 0) {
        if (Math.random() < dt * 0.3) {
          cell.delay = t;
          cell.phase = 0;
        }
      }

      // Run scenario animator
      ANIMATORS[cell.scenario](cell, t);

      // Clamp opacity to variant range
      const [minO, maxO] = config.opacityRange;
      cell.opacity = Math.max(0, Math.min(maxO, cell.opacity));
      if (cell.opacity > 0 && cell.opacity < minO) cell.opacity = minO;

      // Dirty check — only redraw changed cells
      const quantized = Math.round(cell.opacity * 100);
      const prevQuantized = Math.round(cell.prevOpacity * 100);
      if (quantized === prevQuantized) continue;

      const x = cell.col * GRID;
      const y = cell.row * GRID;

      // Clear previous
      if (cell.prevOpacity > 0) {
        ctx.clearRect(x, y, GRID, GRID);
      }

      // Draw new
      if (cell.opacity > 0) {
        ctx.globalAlpha = cell.opacity;
        ctx.fillStyle = cell.color;
        ctx.fillRect(x, y, GRID - 1, GRID - 1); // -1 for grid gap
      }

      cell.prevOpacity = cell.opacity;
    }

    ctx.globalAlpha = 1;
  }, [config.opacityRange]);

  // Setup
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    ctxRef.current = canvas.getContext("2d");
    resize();

    // Start animation
    lastFrameRef.current = performance.now();
    rafRef.current = requestAnimationFrame(animate);

    // Resize listener
    window.addEventListener("resize", resize);

    // Pause when tab hidden
    const onVisibility = () => {
      if (document.hidden) {
        cancelAnimationFrame(rafRef.current);
      } else {
        lastFrameRef.current = performance.now();
        rafRef.current = requestAnimationFrame(animate);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelAnimationFrame(rafRef.current);
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [animate, resize]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 0,
        pointerEvents: "none",
        willChange: "transform",
      }}
    />
  );
}
