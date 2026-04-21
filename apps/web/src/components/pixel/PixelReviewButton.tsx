"use client";

import { useRef, useEffect, useCallback, useState } from "react";
import { pixelFont } from "@/lib/pixel-font";

// ═══════════════════════════════════════════════════════════
//  PixelReviewButton — "★ ОСТАВИТЬ ОТЗЫВ" pixel scroll-in
//  Canvas 2D, IntersectionObserver trigger
// ═══════════════════════════════════════════════════════════

const PAL = {
  bg: "#0e0b1a",
  accent: "#6b4dc7",
  white: "#e8e4f0",
  gold: "#d4a84b",
};

const BUTTON_TEXT = "★ ОСТАВИТЬ ОТЗЫВ";
const FONT_SIZE = 22;
const PIXEL_SIZE = 2;
const ANIM_DURATION = 0.5;

// Pre-tagged dot roles (avoid per-frame string comparison)
const enum DotRole { BG, TEXT, ACCENT }

interface PixelDot {
  tx: number; ty: number;
  cx: number; cy: number;
  sx: number; sy: number;
  delay: number;
  role: DotRole;
}

function easeOutBack(t: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2;
}

function extractPixels(text: string, fontSize: number, pixelSize: number) {
  const off = document.createElement("canvas");
  const ctx = off.getContext("2d")!;
  const font = pixelFont(fontSize);

  ctx.font = font;
  const tw = Math.ceil(ctx.measureText(text).width);
  const th = Math.ceil(fontSize * 1.3);

  const padX = 12, padY = 6;
  off.width = tw + padX * 2;
  off.height = th + padY * 2;

  // Pixelated button background
  ctx.fillStyle = "#231d3a";
  ctx.fillRect(0, 0, off.width, off.height);

  // Thick accent border
  ctx.strokeStyle = PAL.accent;
  ctx.lineWidth = 3;
  ctx.strokeRect(2, 2, off.width - 4, off.height - 4);

  // Text
  ctx.font = font;
  ctx.fillStyle = "#ffffff";
  ctx.textBaseline = "top";
  ctx.fillText(text, padX, padY);

  const imgData = ctx.getImageData(0, 0, off.width, off.height);
  const dots: { x: number; y: number; role: DotRole }[] = [];

  for (let y = 0; y < off.height; y += pixelSize) {
    for (let x = 0; x < off.width; x += pixelSize) {
      const i = (y * off.width + x) * 4;
      const r = imgData.data[i], g = imgData.data[i + 1], b = imgData.data[i + 2], a = imgData.data[i + 3];
      if (a < 30) continue;

      // Classify pixel by color channel ratios (more robust than magic thresholds)
      const isWhite = r > 200 && g > 200 && b > 200;
      const isAccentish = b > 120 && r < b && g < b;
      const role = isWhite ? DotRole.TEXT : isAccentish ? DotRole.ACCENT : DotRole.BG;

      dots.push({ x: Math.floor(x / pixelSize), y: Math.floor(y / pixelSize), role });
    }
  }

  return {
    dots,
    width: Math.ceil(off.width / pixelSize),
    height: Math.ceil(off.height / pixelSize),
  };
}

const ROLE_COLOR: Record<DotRole, string> = {
  [DotRole.BG]: PAL.bg,
  [DotRole.TEXT]: PAL.white,
  [DotRole.ACCENT]: PAL.accent,
};
const ROLE_HOVER_COLOR: Record<DotRole, string> = {
  [DotRole.BG]: "#231d3a",
  [DotRole.TEXT]: PAL.gold,
  [DotRole.ACCENT]: "#9a3bef",
};

interface PixelReviewButtonProps {
  onClick: () => void;
}

export function PixelReviewButton({ onClick }: PixelReviewButtonProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [triggered, setTriggered] = useState(false);
  const hoveredRef = useRef(false);
  const [, forceRender] = useState(0);
  const dotsRef = useRef<PixelDot[]>([]);
  const dimsRef = useRef({ width: 0, height: 0 });
  const startRef = useRef(0);
  const rafRef = useRef(0);

  // IntersectionObserver
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setTriggered(true); obs.disconnect(); } },
      { threshold: 0.5 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  // Init: extract pixels, cache context
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctxRef.current = ctx;

    const { dots, width, height } = extractPixels(BUTTON_TEXT, FONT_SIZE, PIXEL_SIZE);
    dimsRef.current = { width, height };
    canvas.width = width * PIXEL_SIZE;
    canvas.height = height * PIXEL_SIZE;
    forceRender((n) => n + 1); // trigger re-render to update style dims

    dotsRef.current = dots.map((d) => {
      const sx = -20 - Math.random() * 60;
      const sy = d.y + (Math.random() - 0.5) * 30;
      return {
        tx: d.x, ty: d.y,
        cx: sx, cy: sy, sx, sy,
        delay: (d.x / width) * 0.3 + Math.random() * 0.05,
        role: d.role,
      };
    });
  }, []);

  // Stable animate — reads hovered from ref, no dep on hovered state
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

    const isHovered = hoveredRef.current;
    const colorMap = isHovered ? ROLE_HOVER_COLOR : ROLE_COLOR;
    let allDone = true;

    for (const dot of dotsRef.current) {
      const raw = (elapsed - dot.delay) / ANIM_DURATION;
      const t = raw < 0 ? 0 : raw > 1 ? 1 : raw;
      if (t < 1) allDone = false;

      const ease = easeOutBack(t);
      dot.cx = dot.sx + (dot.tx - dot.sx) * ease;
      dot.cy = dot.sy + (dot.ty - dot.sy) * ease;

      ctx.globalAlpha = t < 0.4 ? t * 2.5 : 1;
      ctx.fillStyle = colorMap[dot.role];
      ctx.fillRect(
        Math.round(dot.cx) * PIXEL_SIZE,
        Math.round(dot.cy) * PIXEL_SIZE,
        PIXEL_SIZE, PIXEL_SIZE,
      );
    }

    ctx.globalAlpha = 1;

    // Subtle glow on hover (only when assembled, no per-frame filter)
    if (allDone && isHovered) {
      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = 0.08;
      // Shift-draw for cheap glow (no filter)
      ctx.drawImage(ctx.canvas, 1, 0);
      ctx.drawImage(ctx.canvas, -1, 0);
      ctx.drawImage(ctx.canvas, 0, 1);
      ctx.drawImage(ctx.canvas, 0, -1);
      ctx.restore();
    }

    rafRef.current = requestAnimationFrame(animate);
  }, []);

  // Start on trigger
  useEffect(() => {
    if (!triggered) return;
    startRef.current = 0;
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [triggered, animate]);

  const displayW = dimsRef.current.width * PIXEL_SIZE || undefined;
  const displayH = dimsRef.current.height * PIXEL_SIZE || undefined;

  return (
    <div
      ref={containerRef}
      className="inline-block cursor-pointer"
      onClick={onClick}
      onMouseEnter={() => { hoveredRef.current = true; }}
      onMouseLeave={() => { hoveredRef.current = false; }}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
      aria-label="Оставить отзыв"
    >
      <canvas
        ref={canvasRef}
        className="render-pixel"
        style={{ width: displayW, height: displayH, maxWidth: "100%" }}
      />
    </div>
  );
}
