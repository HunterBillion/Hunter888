"use client";

import { useRef, useEffect, useCallback, useState } from "react";
import { pixelFont } from "@/lib/pixel-font";

// ═══════════════════════════════════════════════════════════
//  PixelTextReveal — "Тренировка → Разбор → Рост"
//  Canvas 2D, IntersectionObserver trigger, pixel assembly
// ═══════════════════════════════════════════════════════════

const PAL = {
  bg: "#0e0b1a",
  accent: "#6b4dc7",
  accentL: "#9a3bef",
  gold: "#d4a84b",
  white: "#e8e4f0",
  muted: "#5a5478",
};

const TEXT = "Тренировка → Разбор → Рост";
const FONT_SIZE = 32;
const PIXEL_SIZE = 2;
const ANIM_DURATION = 0.6;
const LETTER_STAGGER = 0.025;
const GLOW_PULSE_SPEED = 2;

// ── Word-to-color mapping (pre-computed once) ─────────────
const WORD_COLORS: Record<string, string> = {
  "Тренировка": PAL.accent,
  "→": PAL.gold,
  "Разбор": PAL.accentL,
  "Рост": PAL.gold,
};

interface PixelDot {
  tx: number;
  ty: number;
  cx: number;
  cy: number;
  sx: number;
  sy: number;
  delay: number;
  color: string;
}

function easeOutCubic(t: number): number {
  return 1 - (1 - t) ** 3;
}

function easeOutElastic(t: number): number {
  if (t === 0 || t === 1) return t;
  return 2 ** (-10 * t) * Math.sin((t - 0.1) * (2 * Math.PI) / 0.4) + 1;
}

/** Pre-compute which word each character index belongs to */
function buildColorMap(text: string): string[] {
  const colors: string[] = [];
  const words = text.split(" ");
  let pos = 0;
  for (const word of words) {
    const color = WORD_COLORS[word] ?? PAL.white;
    for (let i = 0; i < word.length; i++) {
      colors[pos++] = color;
    }
    colors[pos++] = PAL.muted; // space
  }
  return colors;
}

const COLOR_MAP = buildColorMap(TEXT);

/** Render text to offscreen canvas, extract pixel positions */
function extractPixels(text: string, fontSize: number, pixelSize: number) {
  const off = document.createElement("canvas");
  const ctx = off.getContext("2d")!;
  const font = pixelFont(fontSize);

  ctx.font = font;
  const tw = Math.ceil(ctx.measureText(text).width);
  const th = Math.ceil(fontSize * 1.3);

  off.width = tw + 4;
  off.height = th + 4;

  ctx.font = font;
  ctx.fillStyle = "#ffffff";
  ctx.textBaseline = "top";
  ctx.fillText(text, 2, 2);

  const imgData = ctx.getImageData(0, 0, off.width, off.height);

  // Pre-compute character x boundaries
  const charEdges: number[] = [];
  let cx = 2;
  for (let i = 0; i < text.length; i++) {
    charEdges.push(cx);
    cx += ctx.measureText(text[i]).width;
  }

  const dots: { x: number; y: number; charIdx: number }[] = [];
  for (let y = 0; y < off.height; y += pixelSize) {
    for (let x = 0; x < off.width; x += pixelSize) {
      if (imgData.data[(y * off.width + x) * 4 + 3] > 100) {
        // Binary search for character index
        let lo = 0, hi = charEdges.length - 1;
        while (lo < hi) {
          const mid = (lo + hi + 1) >> 1;
          if (x >= charEdges[mid]) lo = mid; else hi = mid - 1;
        }
        dots.push({ x: Math.floor(x / pixelSize), y: Math.floor(y / pixelSize), charIdx: lo });
      }
    }
  }

  return {
    dots,
    width: Math.ceil(off.width / pixelSize),
    height: Math.ceil(off.height / pixelSize),
  };
}

export function PixelTextReveal() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [triggered, setTriggered] = useState(false);
  const dotsRef = useRef<PixelDot[]>([]);
  const dimsRef = useRef({ width: 0, height: 0 });
  const startRef = useRef(0);
  const rafRef = useRef(0);
  // Pre-rendered glow image (avoids per-frame blur filter)
  const glowCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const allDoneRef = useRef(false);

  // IntersectionObserver
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setTriggered(true); obs.disconnect(); } },
      { threshold: 0.3 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Init: extract pixels, cache context, compute scatter radius responsively
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctxRef.current = ctx;

    const { dots, width, height } = extractPixels(TEXT, FONT_SIZE, PIXEL_SIZE);
    dimsRef.current = { width, height };

    canvas.width = width * PIXEL_SIZE;
    canvas.height = height * PIXEL_SIZE;

    // Responsive scatter: scale to canvas width so it looks right on any viewport
    const scatterRadius = Math.max(40, width * 0.8);
    const centerX = width / 2;
    const centerY = height / 2;

    dotsRef.current = dots.map((d) => {
      const angle = Math.random() * Math.PI * 2;
      const dist = scatterRadius + Math.random() * scatterRadius;
      const sx = centerX + Math.cos(angle) * dist;
      const sy = centerY + Math.sin(angle) * dist;
      return {
        tx: d.x, ty: d.y,
        cx: sx, cy: sy,
        sx, sy,
        delay: d.charIdx * LETTER_STAGGER,
        color: COLOR_MAP[d.charIdx] ?? PAL.white,
      };
    });

    // Draw initial scattered state (faint)
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const dot of dotsRef.current) {
      ctx.fillStyle = dot.color;
      ctx.globalAlpha = 0.12;
      ctx.fillRect(Math.round(dot.cx) * PIXEL_SIZE, Math.round(dot.cy) * PIXEL_SIZE, PIXEL_SIZE, PIXEL_SIZE);
    }
    ctx.globalAlpha = 1;
  }, []);

  // Build glow layer once all pixels have assembled
  const buildGlowCanvas = useCallback(() => {
    const src = canvasRef.current;
    if (!src || glowCanvasRef.current) return;
    const glow = document.createElement("canvas");
    glow.width = src.width;
    glow.height = src.height;
    const g = glow.getContext("2d")!;
    g.filter = "blur(4px)";
    g.drawImage(src, 0, 0);
    g.filter = "none";
    glowCanvasRef.current = glow;
  }, []);

  // Animation loop — cached ctx, no per-frame filter, frame-independent
  const animate = useCallback(() => {
    const ctx = ctxRef.current;
    if (!ctx) return;

    const now = performance.now() / 1000;
    if (startRef.current === 0) startRef.current = now;
    const elapsed = now - startRef.current;

    const { width, height } = dimsRef.current;
    const cw = width * PIXEL_SIZE;
    const ch = height * PIXEL_SIZE;

    ctx.clearRect(0, 0, cw, ch);

    let done = true;

    for (const dot of dotsRef.current) {
      const raw = (elapsed - dot.delay) / ANIM_DURATION;
      const t = raw < 0 ? 0 : raw > 1 ? 1 : raw;

      if (t < 1) done = false;

      // Two-phase easing: cubic approach + elastic settle
      const ease = t < 0.7
        ? easeOutCubic(t / 0.7)
        : 0.95 + easeOutElastic((t - 0.7) / 0.3) * 0.05;
      const e = ease > 1 ? 1 : ease;

      dot.cx = dot.sx + (dot.tx - dot.sx) * e;
      dot.cy = dot.sy + (dot.ty - dot.sy) * e;

      const px = Math.round(dot.cx) * PIXEL_SIZE;
      const py = Math.round(dot.cy) * PIXEL_SIZE;

      if (t >= 1) {
        const pulse = Math.sin(elapsed * GLOW_PULSE_SPEED * Math.PI) * 0.15 + 0.85;
        ctx.globalAlpha = pulse;
      } else {
        ctx.globalAlpha = t < 0.33 ? t * 3 : 1;
      }

      ctx.fillStyle = dot.color;
      ctx.fillRect(px, py, PIXEL_SIZE, PIXEL_SIZE);
    }

    ctx.globalAlpha = 1;

    // Glow overlay — uses pre-rendered blur canvas (no per-frame filter)
    if (done) {
      if (!allDoneRef.current) {
        allDoneRef.current = true;
        // Build glow canvas on first "all done" frame
        requestAnimationFrame(() => buildGlowCanvas());
      }
      if (glowCanvasRef.current) {
        const intensity = Math.sin(elapsed * GLOW_PULSE_SPEED * Math.PI) * 0.3 + 0.3;
        ctx.save();
        ctx.globalCompositeOperation = "lighter";
        ctx.globalAlpha = intensity * 0.15;
        ctx.drawImage(glowCanvasRef.current, 0, 0);
        ctx.restore();
      }
    }

    rafRef.current = requestAnimationFrame(animate);
  }, [buildGlowCanvas]);

  // Start/stop animation on trigger
  useEffect(() => {
    if (!triggered) return;
    startRef.current = 0;
    allDoneRef.current = false;
    glowCanvasRef.current = null;
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [triggered, animate]);

  // Display at native pixel size (already large enough with FONT_SIZE 28 + PIXEL_SIZE 3)
  const displayW = dimsRef.current.width * PIXEL_SIZE || undefined;
  const displayH = dimsRef.current.height * PIXEL_SIZE || undefined;

  return (
    <div ref={containerRef} className="flex items-center justify-start">
      <canvas
        ref={canvasRef}
        className="render-pixel"
        style={{ width: displayW, height: displayH, maxWidth: "100%" }}
      />
    </div>
  );
}
