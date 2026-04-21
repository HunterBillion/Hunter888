"use client";

/**
 * StylizedAvatar — Immersive sci-fi character portrait for training sessions.
 *
 * DiceBear "notionists" portrait + holographic HUD frame:
 * - Emotion-reactive color system with smooth transitions
 * - Audio-reactive sound visualizer rings
 * - Floating ambient particles
 * - Holographic scan line effect
 * - Breathing/idle animation
 * - Emotion change flash + glitch effect
 * - HUD corner indicators
 * - Designed to match X Hunter cyberpunk brand
 */

import { useMemo, useRef, useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from "framer-motion";
import { createAvatar } from "@dicebear/core";
import { notionists } from "@dicebear/collection";
import { EMOTION_MAP, type EmotionState } from "@/types";

// ─── Emotion colors ─────────────────────────────────────────────────────────

const EMOTION_HEX: Record<string, string> = {
  cold: "#64748B",
  hostile: "#EF4444",
  resistant: "#F97316",
  skeptical: "#3B82F6",
  guarded: "#6B4DC7",
  testing: "#EAB308",
  curious: "#10B981",
  warming: "#34D399",
  callback: "#60A5FA",
  open: "#8B5CF6",
  considering: "#7C3AED",
  negotiating: "#A78BFA",
  deal: "#22C55E",
  neutral: "#8B7FC8",
};

function getEmotionColor(emotion: string): string {
  return EMOTION_HEX[emotion] || "#8B7FC8";
}

function getEmotionGlow(emotion: string): string {
  const c = getEmotionColor(emotion);
  return `0 0 40px ${c}30, 0 0 80px ${c}15, 0 0 120px ${c}08`;
}

// ─── Audio Visualizer Ring (Canvas) ─────────────────────────────────────────

function AudioRing({ audioLevel, color, size }: { audioLevel: number; color: string; size: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const barsRef = useRef<number[]>(Array(32).fill(0));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const draw = () => {
      ctx.clearRect(0, 0, size, size);
      const cx = size / 2;
      const cy = size / 2;
      const radius = size / 2 - 8;
      const bars = barsRef.current;
      const barCount = bars.length;

      // Update bars with audio level + randomness
      for (let i = 0; i < barCount; i++) {
        const target = audioLevel * (0.3 + Math.random() * 0.7) * 20;
        bars[i] = bars[i] * 0.85 + target * 0.15;
      }

      ctx.lineCap = "round";
      ctx.lineWidth = 2;

      for (let i = 0; i < barCount; i++) {
        const angle = (i / barCount) * Math.PI * 2 - Math.PI / 2;
        const barH = Math.max(2, bars[i]);
        const x1 = cx + Math.cos(angle) * radius;
        const y1 = cy + Math.sin(angle) * radius;
        const x2 = cx + Math.cos(angle) * (radius + barH);
        const y2 = cy + Math.sin(angle) * (radius + barH);

        const alpha = 0.3 + (barH / 25) * 0.7;
        ctx.strokeStyle = color + Math.round(alpha * 255).toString(16).padStart(2, "0");
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }

      animRef.current = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(animRef.current);
  }, [audioLevel, color, size]);

  return (
    <canvas
      ref={canvasRef}
      width={size}
      height={size}
      className="absolute inset-0 pointer-events-none"
      style={{ width: size, height: size }}
    />
  );
}

// ─── Scan Line Effect ───────────────────────────────────────────────────────

function ScanLine() {
  return (
    <motion.div
      className="absolute left-0 right-0 h-[2px] pointer-events-none z-10"
      style={{
        background: "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.06) 50%, transparent 100%)",
      }}
      animate={{ top: ["0%", "100%"] }}
      transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
    />
  );
}

// ─── Floating Particles ─────────────────────────────────────────────────────

function Particles({ color, count = 16 }: { color: string; count?: number }) {
  const particles = useMemo(() =>
    Array.from({ length: count }, (_, i) => ({
      id: i,
      x: 10 + Math.random() * 80,
      y: 10 + Math.random() * 80,
      size: 1.5 + Math.random() * 2.5,
      duration: 4 + Math.random() * 6,
      delay: Math.random() * 4,
      drift: -15 + Math.random() * 30,
    })), [count]);

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      {particles.map((p) => (
        <motion.div
          key={p.id}
          className="absolute rounded-full"
          style={{
            left: `${p.x}%`,
            top: `${p.y}%`,
            width: p.size,
            height: p.size,
            background: color,
          }}
          animate={{
            y: [0, -30, 0],
            x: [0, p.drift, 0],
            opacity: [0, 0.7, 0],
            scale: [0.3, 1, 0.3],
          }}
          transition={{
            duration: p.duration,
            delay: p.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}

// ─── HUD Corner Brackets ────────────────────────────────────────────────────

function HUDCorners({ color }: { color: string }) {
  const style = { borderColor: `${color}50` };
  return (
    <>
      <div className="absolute top-0 left-0 w-5 h-5 border-l-2 border-t-2 rounded-tl-sm" style={style} />
      <div className="absolute top-0 right-0 w-5 h-5 border-r-2 border-t-2 rounded-tr-sm" style={style} />
      <div className="absolute bottom-0 left-0 w-5 h-5 border-l-2 border-b-2 rounded-bl-sm" style={style} />
      <div className="absolute bottom-0 right-0 w-5 h-5 border-r-2 border-b-2 rounded-br-sm" style={style} />
    </>
  );
}

// ─── Holographic Border Ring ────────────────────────────────────────────────

function HoloBorder({ color, speaking }: { color: string; speaking: boolean }) {
  return (
    <motion.div
      className="absolute inset-[-3px] rounded-full pointer-events-none"
      style={{
        background: `conic-gradient(from 0deg, ${color}00, ${color}60, ${color}00, ${color}40, ${color}00)`,
        WebkitMask: "radial-gradient(farthest-side, transparent calc(100% - 3px), #fff calc(100% - 2px))",
        mask: "radial-gradient(farthest-side, transparent calc(100% - 3px), #fff calc(100% - 2px))",
      }}
      animate={{ rotate: 360 }}
      transition={{ duration: speaking ? 2 : 8, repeat: Infinity, ease: "linear" }}
    />
  );
}

// ─── Main Export ────────────────────────────────────────────────────────────

export interface StylizedAvatarProps {
  emotion?: string;
  isSpeaking?: boolean;
  audioLevel?: number;
  className?: string;
  seed?: string;
}

export function StylizedAvatar({
  emotion = "cold",
  isSpeaking = false,
  audioLevel = 0,
  className = "",
  seed = "default",
}: StylizedAvatarProps) {
  const emotionColor = getEmotionColor(emotion);
  const emotionLabel = EMOTION_MAP[emotion as EmotionState]?.labelRu || "НЕЙТРАЛЬНЫЙ";
  const prevEmotionRef = useRef(emotion);
  const [emotionFlash, setEmotionFlash] = useState(false);
  const [glitch, setGlitch] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Smooth color transition
  const colorProgress = useMotionValue(0);

  // Emotion change effects
  useEffect(() => {
    if (emotion !== prevEmotionRef.current) {
      prevEmotionRef.current = emotion;
      setEmotionFlash(true);
      setGlitch(true);
      animate(colorProgress, 1, { duration: 0.6 });
      const t1 = setTimeout(() => setEmotionFlash(false), 500);
      const t2 = setTimeout(() => setGlitch(false), 150);
      return () => { clearTimeout(t1); clearTimeout(t2); };
    }
  }, [emotion, colorProgress]);

  // Generate DiceBear avatar
  const avatarSvg = useMemo(() => {
    const avatar = createAvatar(notionists, {
      seed: seed,
      size: 320,
      backgroundColor: ["transparent"],
    });
    return `data:image/svg+xml;utf8,${encodeURIComponent(avatar.toString())}`;
  }, [seed]);

  // Container size for audio ring
  const [ringSize, setRingSize] = useState(280);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width || 280;
      setRingSize(Math.min(w, 360));
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <div className={`relative flex items-center justify-center ${className}`} ref={containerRef}>
      {/* Full background glow */}
      <div
        className="absolute inset-0 transition-all duration-1000"
        style={{
          background: `radial-gradient(ellipse at center, ${emotionColor}12 0%, ${emotionColor}05 40%, transparent 70%)`,
        }}
      />

      {/* Ambient particles */}
      <Particles color={emotionColor} count={14} />

      {/* Central avatar area */}
      <div className="relative" style={{ width: ringSize, height: ringSize }}>
        {/* HUD corners */}
        <HUDCorners color={emotionColor} />

        {/* Audio visualizer ring */}
        {isSpeaking && (
          <AudioRing audioLevel={audioLevel} color={emotionColor} size={ringSize} />
        )}

        {/* Portrait container */}
        <div className="absolute inset-[16px] flex items-center justify-center">
          {/* Outer glow */}
          <motion.div
            className="absolute inset-[-6px] rounded-full transition-all duration-700"
            style={{ boxShadow: getEmotionGlow(emotion) }}
            animate={{ scale: [1, 1.02, 1] }}
            transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          />

          {/* Holographic rotating border */}
          <HoloBorder color={emotionColor} speaking={isSpeaking} />

          {/* Emotion flash ring */}
          <AnimatePresence>
            {emotionFlash && (
              <motion.div
                className="absolute inset-[-6px] rounded-full"
                style={{ border: `2px solid ${emotionColor}`, boxShadow: `0 0 30px ${emotionColor}80` }}
                initial={{ scale: 0.9, opacity: 1 }}
                animate={{ scale: 1.15, opacity: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.5 }}
              />
            )}
          </AnimatePresence>

          {/* Avatar circle */}
          <motion.div
            className="relative w-full h-full rounded-full overflow-hidden"
            style={{
              background: "var(--bg-secondary)",
              border: `2px solid ${emotionColor}30`,
            }}
            animate={{
              scale: isSpeaking
                ? [1, 1 + audioLevel * 0.015, 1]
                : [1, 1.01, 1],
            }}
            transition={{
              duration: isSpeaking ? 0.25 : 3.5,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          >
            {/* Scan line */}
            <ScanLine />

            {/* DiceBear portrait */}
            <motion.img
              src={avatarSvg}
              alt="Character"
              className="w-full h-full object-cover"
              style={{ scale: 1.15 }}
              draggable={false}
              animate={glitch ? {
                x: [0, -3, 3, -1, 0],
                filter: [
                  "hue-rotate(0deg)",
                  "hue-rotate(30deg)",
                  "hue-rotate(-20deg)",
                  "hue-rotate(10deg)",
                  "hue-rotate(0deg)",
                ],
              } : {}}
              transition={{ duration: 0.15 }}
            />

            {/* Emotion color overlay */}
            <div
              className="absolute inset-0 transition-colors duration-700 mix-blend-soft-light"
              style={{ background: `${emotionColor}12` }}
            />

            {/* Inner vignette */}
            <div
              className="absolute inset-0"
              style={{ boxShadow: `inset 0 0 40px ${emotionColor}15, inset 0 0 80px rgba(0,0,0,0.2)` }}
            />
          </motion.div>
        </div>

        {/* Status indicators */}
        {isSpeaking && (
          <motion.div
            className="absolute top-1 right-1 w-2.5 h-2.5 rounded-full"
            style={{ background: emotionColor, boxShadow: `0 0 8px ${emotionColor}` }}
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ duration: 0.8, repeat: Infinity }}
          />
        )}

        {/* Emotion value bar (left side) */}
        <div
          className="absolute left-0 top-[20%] bottom-[20%] w-[3px] rounded-full overflow-hidden"
          style={{ background: `${emotionColor}15` }}
        >
          <motion.div
            className="absolute bottom-0 w-full rounded-full"
            style={{ background: emotionColor }}
            animate={{
              height: `${(EMOTION_MAP[emotion as EmotionState]?.value || 0)}%`,
            }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          />
        </div>
      </div>

      {/* Emotion label */}
      <motion.div
        className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-lg px-4 py-2 font-mono text-xs uppercase tracking-widest"
        style={{
          background: "rgba(0,0,0,0.5)",
          backdropFilter: "blur(12px)",
          border: `1px solid ${emotionColor}30`,
          color: emotionColor,
          boxShadow: `0 0 20px ${emotionColor}10`,
        }}
        key={emotion}
        initial={{ y: 8, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.3 }}
      >
        <span
          className="w-2 h-2 rounded-full"
          style={{ background: emotionColor, boxShadow: `0 0 6px ${emotionColor}` }}
        />
        {emotionLabel}
      </motion.div>
    </div>
  );
}
