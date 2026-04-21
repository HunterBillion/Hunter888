"use client";

import { useRef, useEffect, useCallback } from "react";

// ═══════════════════════════════════════════════════════════
//  Pixel Life Cycle — 320×180 Canvas, 25s loop, 5 scenes
// ═══════════════════════════════════════════════════════════

const W = 320;
const H = 180;

// ── Color palette (locked for quantization feel) ──────────
const PAL = {
  bg:        "#0e0b1a",
  bgLight:   "#1a1530",
  panel:     "#231d3a",
  accent:    "#6b4dc7",
  accentL:   "#9a3bef",
  gold:      "#d4a84b",
  green:     "#28c840",
  red:       "#ff5f57",
  white:     "#e8e4f0",
  muted:     "#5a5478",
  skin:      "#f0c8a0",
  shirt:     "#4a8ef0",
  torch:     "#ff8800",
  torchGlow: "#ff440044",
  monster1:  "#e04040",
  monster2:  "#e08020",
  monster3:  "#8040e0",
};

// ── Scene timing ──────────────────────────────────────────
const SCENES = [
  { name: "OFFICE",    start: 0,    dur: 5,   trans: 0.5 },
  { name: "DUNGEON",   start: 5.5,  dur: 5,   trans: 0.5 },
  { name: "ANALYTICS", start: 11,   dur: 4,   trans: 0.5 },
  { name: "ARENA",     start: 15.5, dur: 4,   trans: 0.5 },
  { name: "PODIUM",    start: 20,   dur: 5,   trans: 0 },
] as const;
const LOOP = 25;

type SceneName = typeof SCENES[number]["name"];

// ── Tiny pixel sprite renderer ────────────────────────────
// Sprite data: string[] where each char maps to a color
function drawSprite(ctx: CanvasRenderingContext2D, x: number, y: number, data: string[], colors: Record<string, string>, scale = 1) {
  for (let r = 0; r < data.length; r++) {
    for (let c = 0; c < data[r].length; c++) {
      const ch = data[r][c];
      if (ch === "." || ch === " ") continue;
      const color = colors[ch];
      if (!color) continue;
      ctx.fillStyle = color;
      ctx.fillRect(x + c * scale, y + r * scale, scale, scale);
    }
  }
}

// ── Character sprites ─────────────────────────────────────
const MANAGER_IDLE = [
  "..HHH..",
  ".HHHHH.",
  "..SSS..",
  ".SSSSS.",
  "SSSSSSS",
  ".SSSSS.",
  "..SSS..",
  "..P.P..",
  "..P.P..",
];
const MANAGER_RUN = [
  "..HHH..",
  ".HHHHH.",
  "..SSS..",
  ".SSSSS.",
  "SSSSSSS",
  ".SSSSS.",
  "..SSS..",
  ".P...P.",
  "P.....P",
];
const MANAGER_ATTACK = [
  "..HHH..",
  ".HHHHH.",
  "..SSS.A",
  ".SSSSA.",
  "SSSSSAA",
  ".SSSSS.",
  "..SSS..",
  "..P.P..",
  "..P.P..",
];
const MANAGER_COLORS: Record<string, string> = { H: PAL.skin, S: PAL.shirt, P: "#334", A: PAL.gold };

const MONSTER_SPRITE = [
  ".MMMM.",
  "MMMMMM",
  "M.WM.W",
  "MMMMMM",
  "M.MM.M",
  "MMMMMM",
  ".M..M.",
];

const TROPHY_SPRITE = [
  ".GGG.",
  "GGGGG",
  ".GGG.",
  "..G..",
  ".GGG.",
];

// ── Particle system ───────────────────────────────────────
interface Particle {
  x: number; y: number; vx: number; vy: number;
  color: string; size: number; life: number; maxLife: number;
  text?: string;
}

function spawnParticles(
  arr: Particle[], x: number, y: number, count: number,
  colors: string[], opts?: { vy?: number; spread?: number; size?: number; life?: number; text?: string }
) {
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 0.5 + Math.random() * (opts?.spread ?? 2);
    const life = opts?.life ?? (0.5 + Math.random() * 1);
    arr.push({
      x, y,
      vx: Math.cos(angle) * speed,
      vy: opts?.vy ?? (Math.sin(angle) * speed - 1),
      color: colors[Math.floor(Math.random() * colors.length)],
      size: opts?.size ?? (Math.random() > 0.5 ? 2 : 1),
      life, maxLife: life,
      text: opts?.text,
    });
  }
}

function updateParticles(particles: Particle[], dt: number) {
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx;
    p.y += p.vy;
    if (!p.text) p.vy += 0.05; // gravity
    p.life -= dt;
    if (p.life <= 0) particles.splice(i, 1);
  }
}

function drawParticles(ctx: CanvasRenderingContext2D, particles: Particle[]) {
  for (const p of particles) {
    const alpha = Math.max(0, p.life / p.maxLife);
    ctx.globalAlpha = alpha;
    if (p.text) {
      ctx.fillStyle = p.color;
      ctx.font = "bold 6px monospace";
      ctx.fillText(p.text, Math.floor(p.x), Math.floor(p.y));
    } else {
      ctx.fillStyle = p.color;
      ctx.fillRect(Math.floor(p.x), Math.floor(p.y), p.size, p.size);
    }
  }
  ctx.globalAlpha = 1;
}

// ── Speech bubble ─────────────────────────────────────────
function drawBubble(ctx: CanvasRenderingContext2D, x: number, y: number, text: string, progress: number) {
  if (progress <= 0) return;
  const chars = Math.floor(text.length * Math.min(progress, 1));
  const shown = text.substring(0, chars);
  ctx.font = "5px monospace";
  const tw = ctx.measureText(shown).width;
  const bw = Math.max(tw + 8, 20);
  const bh = 12;
  const bx = x - bw / 2;
  const by = y - bh - 4;

  ctx.fillStyle = PAL.white;
  ctx.fillRect(bx, by, bw, bh);
  // Pointer triangle
  ctx.fillRect(x - 1, by + bh, 3, 2);

  ctx.fillStyle = PAL.bg;
  ctx.fillText(shown, bx + 4, by + 8);
}

// ── Bar chart (Analytics scene) ───────────────────────────
function drawBarChart(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, progress: number) {
  const bars = [
    { label: "Скрипт", val: 82, color: PAL.green },
    { label: "Возражен", val: 61, color: PAL.muted },
    { label: "Коммуник", val: 73, color: PAL.accent },
    { label: "Эмпатия", val: 92, color: PAL.gold },
  ];
  const barW = Math.floor((w - 8) / bars.length) - 2;
  const chartH = h - 14;

  // Axes
  ctx.fillStyle = PAL.muted;
  ctx.fillRect(x, y, 1, chartH);
  ctx.fillRect(x, y + chartH, w, 1);

  for (let i = 0; i < bars.length; i++) {
    const b = bars[i];
    const bh = (b.val / 100) * chartH * Math.min(progress * 2, 1);
    const bx = x + 4 + i * (barW + 2);
    const by = y + chartH - bh;
    ctx.fillStyle = b.color;
    ctx.fillRect(bx, by, barW, bh);
    // Value text
    if (progress > 0.5) {
      ctx.fillStyle = PAL.white;
      ctx.font = "4px monospace";
      ctx.fillText(`${b.val}`, bx, by - 2);
    }
  }
}

// ── Level badge ───────────────────────────────────────────
function drawLevelBadge(ctx: CanvasRenderingContext2D, x: number, y: number, level: number, flash: number) {
  if (flash > 0) {
    ctx.fillStyle = PAL.accentL;
    ctx.globalAlpha = flash;
    ctx.fillRect(x - 12, y - 12, 24, 24);
    ctx.globalAlpha = 1;
  }
  ctx.fillStyle = PAL.accent;
  ctx.fillRect(x - 8, y - 5, 16, 10);
  ctx.fillStyle = PAL.white;
  ctx.font = "bold 7px monospace";
  ctx.textAlign = "center";
  ctx.fillText(`Lv${level}`, x, y + 3);
  ctx.textAlign = "left";
}

// ══════════════════════════════════════════════════════════
//  SCENE RENDERERS
// ══════════════════════════════════════════════════════════

function drawOffice(ctx: CanvasRenderingContext2D, t: number, particles: Particle[]) {
  // Background: office
  ctx.fillStyle = PAL.bgLight;
  ctx.fillRect(0, 0, W, H);
  // Floor
  ctx.fillStyle = "#2a2540";
  ctx.fillRect(0, 140, W, 40);
  // Floor line
  ctx.fillStyle = PAL.muted;
  ctx.fillRect(0, 140, W, 1);

  // Kanban board on wall
  ctx.fillStyle = PAL.panel;
  ctx.fillRect(40, 30, 80, 50);
  ctx.fillStyle = PAL.muted;
  ctx.fillRect(40, 30, 80, 1);
  ctx.fillRect(40, 30, 1, 50);
  ctx.fillRect(119, 30, 1, 50);
  ctx.fillRect(40, 79, 80, 1);
  // Column dividers
  ctx.fillRect(66, 31, 1, 48);
  ctx.fillRect(93, 31, 1, 48);
  // Cards
  const cardColors = [PAL.accent, PAL.green, PAL.gold, PAL.red, PAL.accentL];
  for (let col = 0; col < 3; col++) {
    for (let row = 0; row < (col === 1 ? 3 : 2); row++) {
      ctx.fillStyle = cardColors[(col * 3 + row) % cardColors.length];
      ctx.fillRect(43 + col * 27, 34 + row * 14, 20, 10);
    }
  }

  // Desk
  ctx.fillStyle = "#3a3058";
  ctx.fillRect(140, 115, 60, 5);
  // Monitor
  ctx.fillStyle = "#222";
  ctx.fillRect(155, 90, 30, 22);
  ctx.fillStyle = PAL.accent;
  ctx.fillRect(157, 92, 26, 18);
  // Monitor stand
  ctx.fillStyle = "#444";
  ctx.fillRect(167, 112, 6, 3);

  // Manager character (idle with breathing)
  const breathOffset = Math.sin(t * 2) * 0.5;
  const blink = Math.sin(t * 5) > 0.95;
  const sprite = MANAGER_IDLE;
  const mx = 240;
  const my = 120 + breathOffset;
  drawSprite(ctx, mx, my, sprite, MANAGER_COLORS, 2);
  // Eyes
  if (!blink) {
    ctx.fillStyle = "#222";
    ctx.fillRect(mx + 2, my + 4, 2, 2);
    ctx.fillRect(mx + 8, my + 4, 2, 2);
  }

  // Speech bubble
  const bubbleProgress = Math.max(0, (t - 1.5) * 1.5);
  drawBubble(ctx, mx + 7, my - 2, "Клиенты ждут...", bubbleProgress);

  // Floating paper particles
  if (t > 0.5 && Math.random() < 0.03) {
    spawnParticles(particles, 100 + Math.random() * 100, 50, 1, [PAL.white, PAL.muted], { vy: 0.3, spread: 0.3, size: 2, life: 3 });
  }
  drawParticles(ctx, particles);
}

function drawDungeon(ctx: CanvasRenderingContext2D, t: number, particles: Particle[]) {
  // Dark dungeon bg
  ctx.fillStyle = "#0a0815";
  ctx.fillRect(0, 0, W, H);
  // Stone floor
  ctx.fillStyle = "#1a1630";
  ctx.fillRect(0, 140, W, 40);
  // Stone blocks
  for (let bx = 0; bx < W; bx += 20) {
    ctx.fillStyle = "#1e1a35";
    ctx.fillRect(bx, 140, 19, 1);
    ctx.fillRect(bx + (bx % 40 === 0 ? 10 : 0), 155, 1, 25);
  }

  // Torches
  for (const tx of [40, 160, 280]) {
    ctx.fillStyle = "#5a4020";
    ctx.fillRect(tx, 80, 3, 30);
    // Flame
    const flicker = Math.sin(t * 8 + tx) * 2;
    ctx.fillStyle = PAL.torch;
    ctx.fillRect(tx - 2, 72 + flicker, 7, 8);
    ctx.fillStyle = "#ff4400";
    ctx.fillRect(tx - 1, 70 + flicker, 5, 4);
    // Glow
    ctx.fillStyle = "rgba(255,136,0,0.05)";
    ctx.fillRect(tx - 20, 60, 43, 60);
  }

  // Manager running/attacking
  const mx = Math.min(60 + t * 30, 180);
  const attacking = t > 2 && t < 4.5;
  const sprite = attacking ? MANAGER_ATTACK : (t > 0.5 ? MANAGER_RUN : MANAGER_IDLE);
  const runBob = Math.sin(t * 12) * 1.5;
  drawSprite(ctx, mx, 118 + runBob, sprite, MANAGER_COLORS, 2);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(mx + 2, 122 + runBob, 2, 2);
  ctx.fillRect(mx + 8, 122 + runBob, 2, 2);

  // Monsters
  const monsters = [
    { label: "НЕТ", color: PAL.monster1, x: 220, hitAt: 2.5 },
    { label: "ДОРОГО", color: PAL.monster2, x: 250, hitAt: 3.2 },
    { label: "ПОДУМАЮ", color: PAL.monster3, x: 280, hitAt: 4.0 },
  ];

  for (const m of monsters) {
    if (t < m.hitAt - 1.5) {
      // Monster alive — approaching
      const mxPos = m.x - Math.max(0, t - 0.5) * 8;
      const monsterColors: Record<string, string> = { M: m.color, W: PAL.white };
      const bob = Math.sin(t * 6 + m.x) * 1;
      drawSprite(ctx, mxPos, 122 + bob, MONSTER_SPRITE, monsterColors, 2);
      // Label
      ctx.fillStyle = PAL.white;
      ctx.font = "4px monospace";
      ctx.textAlign = "center";
      ctx.fillText(m.label, mxPos + 6, 118 + bob);
      ctx.textAlign = "left";
    } else if (t < m.hitAt) {
      // Hit flash
      ctx.fillStyle = PAL.white;
      ctx.globalAlpha = 1 - (t - (m.hitAt - 0.3)) * 3;
      ctx.fillRect(m.x - 30, 110, 30, 30);
      ctx.globalAlpha = 1;
    }
    // Spawn explosion particles on hit
    if (Math.abs(t - m.hitAt) < 0.05) {
      spawnParticles(particles, m.x - 20, 130, 15, [m.color, PAL.white, PAL.gold], { spread: 3 });
      spawnParticles(particles, m.x - 20, 120, 1, [PAL.gold], { vy: -1, life: 1.5, text: "+50 XP", size: 1 });
    }
  }

  // Chat bubble (AI dialog)
  if (t > 1.5 && t < 3) {
    drawBubble(ctx, mx + 7, 110, "Чем могу помочь?", (t - 1.5) * 2);
  }

  drawParticles(ctx, particles);
}

function drawAnalytics(ctx: CanvasRenderingContext2D, t: number, particles: Particle[]) {
  // Dashboard bg
  ctx.fillStyle = PAL.bgLight;
  ctx.fillRect(0, 0, W, H);

  // Dashboard frame
  ctx.fillStyle = PAL.panel;
  ctx.fillRect(10, 10, 180, 160);
  ctx.fillStyle = PAL.muted;
  ctx.fillRect(10, 10, 180, 1);

  // Title
  ctx.fillStyle = PAL.white;
  ctx.font = "6px monospace";
  ctx.fillText("Аналитика звонка #47", 16, 24);

  // Bar chart
  drawBarChart(ctx, 20, 35, 160, 80, t / 2);

  // Score counter
  if (t > 1) {
    const score = Math.floor(87 + Math.min((t - 1) * 5, 5));
    ctx.fillStyle = PAL.gold;
    ctx.font = "bold 10px monospace";
    ctx.fillText(`Score: ${score}/100`, 20, 135);
  }

  // Level up effect
  if (t > 2.5 && t < 4) {
    const flash = Math.max(0, 1 - (t - 2.5) * 2);
    drawLevelBadge(ctx, 260, 60, 3, flash);

    // "Level 2 → 3" text
    ctx.fillStyle = PAL.accentL;
    ctx.font = "bold 8px monospace";
    ctx.textAlign = "center";
    ctx.fillText("Level 2 → 3", 260, 85);
    ctx.textAlign = "left";

    if (Math.abs(t - 2.6) < 0.05) {
      spawnParticles(particles, 260, 60, 20, [PAL.accent, PAL.accentL, PAL.gold, PAL.white], { spread: 4, life: 1.5 });
    }
  }

  // Hearts/trophies floating up
  if (t > 1.5 && Math.random() < 0.04) {
    spawnParticles(particles, 220 + Math.random() * 80, 150, 1, [PAL.gold, PAL.green], { vy: -0.8, spread: 0.3, text: "♥", life: 2 });
  }

  // Right panel: rank card
  ctx.fillStyle = PAL.panel;
  ctx.fillRect(200, 10, 110, 70);
  ctx.fillStyle = PAL.white;
  ctx.font = "5px monospace";
  ctx.fillText("Текущий ранг", 208, 24);
  ctx.fillStyle = PAL.gold;
  ctx.font = "bold 8px monospace";
  ctx.fillText("Silver III", 208, 38);
  // Rank bar
  ctx.fillStyle = "#333";
  ctx.fillRect(208, 48, 90, 6);
  ctx.fillStyle = PAL.accent;
  ctx.fillRect(208, 48, Math.min(t * 15, 72), 6);

  drawParticles(ctx, particles);
}

function drawArena(ctx: CanvasRenderingContext2D, t: number, particles: Particle[]) {
  // Arena bg
  ctx.fillStyle = "#12091e";
  ctx.fillRect(0, 0, W, H);
  // Arena floor (colosseum)
  ctx.fillStyle = "#2a1a40";
  ctx.fillRect(0, 130, W, 50);
  // Arena arc columns
  for (const ax of [30, 100, 170, 240, 290]) {
    ctx.fillStyle = "#3a2a55";
    ctx.fillRect(ax, 40, 8, 90);
    ctx.fillRect(ax - 4, 36, 16, 6);
  }
  // Crowd (pixel dots)
  for (let cx = 0; cx < W; cx += 6) {
    for (let cy = 20; cy < 40; cy += 6) {
      ctx.fillStyle = ["#4a3a60", "#3a2a50", "#5a4a70"][(cx + cy) % 3];
      ctx.fillRect(cx, cy, 4, 4);
    }
  }

  // VS flash at start
  if (t < 1) {
    ctx.fillStyle = PAL.white;
    ctx.globalAlpha = 1 - t;
    ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = 1;
    ctx.fillStyle = PAL.red;
    ctx.font = "bold 20px monospace";
    ctx.textAlign = "center";
    ctx.fillText("VS", W / 2, H / 2 + 6);
    ctx.textAlign = "left";
  }

  // Two fighters
  const clashTime = t > 1.5 && t < 3;
  const p1x = clashTime ? Math.min(80 + (t - 1.5) * 40, 140) : 80;
  const p2x = clashTime ? Math.max(240 - (t - 1.5) * 40, 170) : 240;

  // Player (manager)
  const p1sprite = clashTime ? MANAGER_ATTACK : MANAGER_IDLE;
  drawSprite(ctx, p1x, 108, p1sprite, MANAGER_COLORS, 2);
  ctx.fillStyle = "#222";
  ctx.fillRect(p1x + 2, 112, 2, 2);
  ctx.fillRect(p1x + 8, 112, 2, 2);

  // Opponent
  const oppColors: Record<string, string> = { H: "#c0a080", S: PAL.red, P: "#334", A: "#888" };
  const oppSprite = clashTime ? MANAGER_ATTACK : MANAGER_IDLE;
  // Flip horizontally by drawing mirrored
  ctx.save();
  ctx.scale(-1, 1);
  drawSprite(ctx, -p2x - 14, 108, oppSprite, oppColors, 2);
  ctx.restore();

  // Clash sparks
  if (clashTime && Math.random() < 0.1) {
    spawnParticles(particles, 155, 120, 5, [PAL.white, PAL.gold, PAL.accentL], { spread: 3 });
  }

  // Winner celebration
  if (t > 3) {
    // Opponent fades
    ctx.fillStyle = PAL.bg;
    ctx.globalAlpha = Math.min((t - 3) * 2, 0.9);
    ctx.fillRect(p2x - 5, 100, 30, 50);
    ctx.globalAlpha = 1;

    // "ПОБЕДА!" text
    if (t > 3.3) {
      ctx.fillStyle = PAL.gold;
      ctx.font = "bold 12px monospace";
      ctx.textAlign = "center";
      ctx.fillText("ПОБЕДА!", W / 2, 70);
      ctx.textAlign = "left";
    }

    // Confetti
    if (Math.abs(t - 3.2) < 0.05) {
      spawnParticles(particles, W / 2, 80, 30, [PAL.gold, PAL.accent, PAL.accentL, PAL.green, PAL.red], { spread: 4, life: 2 });
    }
  }

  // Name labels
  ctx.font = "5px monospace";
  ctx.fillStyle = PAL.white;
  ctx.textAlign = "center";
  ctx.fillText("Вы", p1x + 7, 103);
  if (t < 3.5) ctx.fillText("Соперник", p2x + 7, 103);
  ctx.textAlign = "left";

  drawParticles(ctx, particles);
}

function drawPodium(ctx: CanvasRenderingContext2D, t: number, particles: Particle[]) {
  // Bg: dark with spotlights
  ctx.fillStyle = "#08061a";
  ctx.fillRect(0, 0, W, H);

  // Spotlights
  const spotAlpha = 0.06 + Math.sin(t * 2) * 0.02;
  ctx.fillStyle = `rgba(107, 77, 199, ${spotAlpha})`;
  // Left spot
  ctx.beginPath();
  ctx.moveTo(80, 0);
  ctx.lineTo(40, 180);
  ctx.lineTo(120, 180);
  ctx.fill();
  // Center spot
  ctx.beginPath();
  ctx.moveTo(160, 0);
  ctx.lineTo(120, 180);
  ctx.lineTo(200, 180);
  ctx.fill();
  // Right spot
  ctx.beginPath();
  ctx.moveTo(240, 0);
  ctx.lineTo(200, 180);
  ctx.lineTo(280, 180);
  ctx.fill();

  // Podium
  ctx.fillStyle = "#2a1a50";
  ctx.fillRect(100, 130, 40, 10); // 2nd place
  ctx.fillRect(140, 120, 40, 20); // 1st place
  ctx.fillRect(180, 135, 40, 5);  // 3rd place
  // Numbers
  ctx.fillStyle = PAL.gold;
  ctx.font = "bold 8px monospace";
  ctx.textAlign = "center";
  ctx.fillText("1", 160, 118);
  ctx.fillStyle = PAL.muted;
  ctx.fillText("2", 120, 128);
  ctx.fillText("3", 200, 133);
  ctx.textAlign = "left";

  // Manager on #1
  const bounce = t > 0.5 ? Math.abs(Math.sin(t * 4)) * 2 : 0;
  drawSprite(ctx, 152, 96 - bounce, MANAGER_IDLE, MANAGER_COLORS, 2);
  ctx.fillStyle = "#222";
  ctx.fillRect(154, 100 - bounce, 2, 2);
  ctx.fillRect(160, 100 - bounce, 2, 2);

  // Trophy
  const trophyColors: Record<string, string> = { G: PAL.gold };
  if (t > 1) drawSprite(ctx, 155, 82 - bounce, TROPHY_SPRITE, trophyColors, 2);

  // "+1200 к рейтингу" text
  if (t > 1.5) {
    const textAlpha = Math.min((t - 1.5) * 2, 1);
    ctx.globalAlpha = textAlpha;
    ctx.fillStyle = PAL.gold;
    ctx.font = "bold 10px monospace";
    ctx.textAlign = "center";
    ctx.fillText("+1200 к рейтингу", W / 2, 40);
    ctx.textAlign = "left";
    ctx.globalAlpha = 1;
  }

  // Fireworks
  if (t > 0.8 && Math.random() < 0.06) {
    const fx = 30 + Math.random() * 260;
    const fy = 20 + Math.random() * 40;
    spawnParticles(particles, fx, fy, 12, [PAL.gold, PAL.accentL, PAL.accent, PAL.white, PAL.red], { spread: 3, life: 1 });
  }

  // Glitch text
  if (t > 3 && t < 4.5) {
    const glitchOffset = Math.random() > 0.7 ? Math.floor(Math.random() * 4 - 2) : 0;
    ctx.fillStyle = PAL.green;
    ctx.font = "5px monospace";
    ctx.textAlign = "center";
    ctx.fillText("Error 404: усталость не найдена", W / 2 + glitchOffset, 60);
    ctx.textAlign = "left";
  }

  // "Level up!" with star particles
  if (t > 2 && t < 3.5) {
    ctx.fillStyle = PAL.accentL;
    ctx.font = "bold 8px monospace";
    ctx.textAlign = "center";
    ctx.fillText("Level up!", W / 2, 155);
    ctx.textAlign = "left";
    if (Math.random() < 0.08) {
      spawnParticles(particles, 140 + Math.random() * 40, 150, 3, [PAL.gold, PAL.white], { vy: -1, spread: 1.5, text: "★", life: 1 });
    }
  }

  // Stage label
  ctx.fillStyle = PAL.muted;
  ctx.font = "4px monospace";
  ctx.textAlign = "center";
  ctx.fillText("Тренировка → Разбор → Рост", W / 2, H - 4);
  ctx.textAlign = "left";

  drawParticles(ctx, particles);
}

// ── Transitions ───────────────────────────────────────────
function drawTransition(ctx: CanvasRenderingContext2D, from: SceneName, progress: number) {
  if (from === "OFFICE") {
    // Portal wipe (purple circle expanding)
    const radius = progress * Math.max(W, H);
    ctx.fillStyle = PAL.accent;
    ctx.globalAlpha = 0.8;
    ctx.beginPath();
    ctx.arc(W / 2, H / 2, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
    if (progress > 0.7) {
      ctx.fillStyle = PAL.white;
      ctx.globalAlpha = (progress - 0.7) * 3;
      ctx.fillRect(0, 0, W, H);
      ctx.globalAlpha = 1;
    }
  } else if (from === "DUNGEON") {
    // Swipe left
    const sw = progress * W;
    ctx.fillStyle = PAL.bg;
    ctx.fillRect(W - sw, 0, sw, H);
  } else if (from === "ANALYTICS") {
    // VS flash
    ctx.fillStyle = PAL.white;
    ctx.globalAlpha = Math.sin(progress * Math.PI);
    ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = 1;
  } else if (from === "ARENA") {
    // Scroll up
    const sh = progress * H;
    ctx.fillStyle = PAL.bg;
    ctx.fillRect(0, 0, W, sh);
  } else {
    // Dissolve
    ctx.fillStyle = PAL.bg;
    ctx.globalAlpha = progress;
    ctx.fillRect(0, 0, W, H);
    ctx.globalAlpha = 1;
  }
}

// ── CRT scanlines (drawn on canvas) ──────────────────────
function drawCRT(ctx: CanvasRenderingContext2D) {
  ctx.fillStyle = "rgba(0,0,0,0.06)";
  for (let y = 0; y < H; y += 2) {
    ctx.fillRect(0, y, W, 1);
  }
}

// ══════════════════════════════════════════════════════════
//  MAIN COMPONENT
// ══════════════════════════════════════════════════════════

export function PixelLifeCycle({ className = "" }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particles = useRef<Particle[]>([]);
  const startTime = useRef(0);

  const render = useCallback((ctx: CanvasRenderingContext2D, now: number) => {
    if (startTime.current === 0) startTime.current = now;
    const elapsed = (now - startTime.current) / 1000;
    const loopTime = elapsed % LOOP;

    // Determine current scene
    let currentScene: typeof SCENES[number] = SCENES[0];
    let sceneLocalTime = loopTime;
    let inTransition = false;
    let transFrom: SceneName = "OFFICE";
    let transProgress = 0;

    for (let i = SCENES.length - 1; i >= 0; i--) {
      if (loopTime >= SCENES[i].start) {
        currentScene = SCENES[i];
        sceneLocalTime = loopTime - currentScene.start;
        break;
      }
    }

    // Check if we're in a transition gap
    for (let i = 0; i < SCENES.length - 1; i++) {
      const sceneEnd = SCENES[i].start + SCENES[i].dur;
      const nextStart = SCENES[i + 1].start;
      if (loopTime >= sceneEnd && loopTime < nextStart) {
        inTransition = true;
        transFrom = SCENES[i].name;
        transProgress = (loopTime - sceneEnd) / (nextStart - sceneEnd);
        // Still show previous scene underneath
        currentScene = SCENES[i];
        sceneLocalTime = SCENES[i].dur;
        break;
      }
    }
    // Loop transition (PODIUM → OFFICE)
    if (loopTime >= SCENES[4].start + SCENES[4].dur) {
      inTransition = true;
      transFrom = "PODIUM";
      transProgress = (loopTime - (SCENES[4].start + SCENES[4].dur)) / 0.5;
    }

    // Clear
    ctx.clearRect(0, 0, W, H);
    ctx.imageSmoothingEnabled = false;

    // Draw current scene
    const dt = 1 / 60;
    switch (currentScene.name) {
      case "OFFICE":    drawOffice(ctx, sceneLocalTime, particles.current); break;
      case "DUNGEON":   drawDungeon(ctx, sceneLocalTime, particles.current); break;
      case "ANALYTICS": drawAnalytics(ctx, sceneLocalTime, particles.current); break;
      case "ARENA":     drawArena(ctx, sceneLocalTime, particles.current); break;
      case "PODIUM":    drawPodium(ctx, sceneLocalTime, particles.current); break;
    }

    // Update particles
    updateParticles(particles.current, dt);

    // Draw transition overlay
    if (inTransition) {
      drawTransition(ctx, transFrom, transProgress);
    }

    // CRT scanlines
    drawCRT(ctx);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;

    let raf: number;
    const loop = (now: number) => {
      render(ctx, now);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [render]);

  return (
    <div className={`relative overflow-hidden ${className}`}>
      <canvas
        ref={canvasRef}
        width={W}
        height={H}
        className="render-pixel block w-full h-full"
      />
      {/* CRT vignette overlay */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at 50% 50%, transparent 60%, rgba(0,0,0,0.4) 100%)",
          boxShadow: "inset 0 0 60px rgba(0,0,0,0.3)",
        }}
      />
    </div>
  );
}
