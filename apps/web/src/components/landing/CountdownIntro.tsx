"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { EASE_SNAP } from "@/lib/constants";

/* ── Sales & psychology quotes for the finale ─────────────────────────────── */
const QUOTES: { text: string; highlight: string }[] = [
  {
    text: "Каждое «нет» приближает тебя к",
    highlight: "«да».",
  },
  {
    text: "Победа куётся до сделки —",
    highlight: "в тренировке.",
  },
  {
    text: "Возражение — не стена. Это дверь,",
    highlight: "которую ты умеешь открывать.",
  },
  {
    text: "Продажи — это передача уверенности.",
    highlight: "Тренируй её каждый день.",
  },
  {
    text: "Лучший переговорщик —",
    highlight: "тот, кто больше всего практиковался.",
  },
];

interface CountdownIntroProps {
  onDone: () => void;
}

/** Full-screen countdown intro: 9 999 999 → 1 → sales quote → fade out */
export function CountdownIntro({ onDone }: CountdownIntroProps) {
  const [display, setDisplay] = useState(9_999_999);
  const [phase, setPhase] = useState<"count" | "moment" | "quote" | "exit">("count");
  // Smooth progress value for the circular indicator (0 → 1)
  const [progress, setProgress] = useState(0);
  const quote = useRef(QUOTES[Math.floor(Math.random() * QUOTES.length)]);

  useEffect(() => {
    const START_MS  = 500;  // hold 9 999 999 for 500 ms
    const COUNT_MS  = 2800; // count from 9 999 999 → 1 over 2.8 s (smoother)
    const MOMENT_AT = 2200; // "Одно Мгновение до..." appears at this ms into the count
    const QUOTE_MS  = 2400; // quote display duration before exit
    const EXIT_MS   = 800;  // fade-out duration

    let rafId: number;
    let countStart: number | null = null;
    let momentFired = false;
    const timers: ReturnType<typeof setTimeout>[] = [];

    const tick = (now: number) => {
      if (countStart === null) countStart = now;
      const elapsed = now - countStart;
      const p = Math.min(elapsed / COUNT_MS, 1);

      // Smooth cubic ease for progress indicator
      setProgress(p);

      // Exponential ease: fast at start, dramatically slows as it approaches 1
      const num = Math.max(1, Math.round(9_999_999 * Math.pow(1 - p, 3)));
      setDisplay(num);

      if (!momentFired && elapsed >= MOMENT_AT) {
        momentFired = true;
        setPhase("moment");
      }

      if (p < 1) {
        rafId = requestAnimationFrame(tick);
      } else {
        setDisplay(1);
        setProgress(1);
        // Brief pause at "1" before showing quote
        timers.push(setTimeout(() => setPhase("quote"), 400));
        timers.push(setTimeout(() => setPhase("exit"),  400 + QUOTE_MS));
        timers.push(setTimeout(onDone,                  400 + QUOTE_MS + EXIT_MS));
      }
    };

    // Hold the initial number before starting the countdown
    const holdTimer = setTimeout(() => {
      rafId = requestAnimationFrame(tick);
    }, START_MS);
    timers.push(holdTimer);

    return () => {
      timers.forEach(clearTimeout);
      cancelAnimationFrame(rafId);
    };
  }, [onDone]);

  const numStr = display.toLocaleString("ru-RU");
  const circumference = 2 * Math.PI * 52;

  return (
    <motion.div
      className="fixed inset-0 z-[9999] flex flex-col items-center justify-center overflow-hidden"
      style={{ background: "var(--bg-primary)" }}
      animate={phase === "exit" ? { opacity: 0 } : { opacity: 1 }}
      transition={phase === "exit" ? { duration: 0.75, ease: [0.4, 0, 0.2, 1] } : { duration: 0.01 }}
    >
      {/* Background dot grid — matches app grid */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `radial-gradient(circle, var(--grid-dot-color, rgba(99,102,241,0.22)) 1px, transparent 1px)`,
          backgroundSize: "24px 24px",
          maskImage: "radial-gradient(ellipse at center, black 20%, rgba(0,0,0,0.3) 70%, transparent 100%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 20%, rgba(0,0,0,0.3) 70%, transparent 100%)",
        }}
      />

      {/* Central accent radial glow — breathing */}
      <motion.div
        className="absolute inset-0 pointer-events-none"
        animate={{ opacity: [0.6, 1, 0.6] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        style={{
          background: "radial-gradient(ellipse at 50% 50%, rgba(99,102,241,0.18) 0%, transparent 60%)",
        }}
      />

      {/* ── Circular progress ring ── */}
      {phase !== "quote" && phase !== "exit" && (
        <div className="absolute pointer-events-none" style={{ width: 120, height: 120 }}>
          <svg width="120" height="120" viewBox="0 0 120 120" className="rotate-[-90deg]">
            <circle
              cx="60" cy="60" r="52"
              fill="none"
              stroke="rgba(99,102,241,0.1)"
              strokeWidth="2"
            />
            <circle
              cx="60" cy="60" r="52"
              fill="none"
              stroke="var(--accent)"
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - progress)}
              style={{
                transition: "stroke-dashoffset 0.05s linear",
                filter: "drop-shadow(0 0 6px var(--accent-glow))",
              }}
            />
          </svg>
        </div>
      )}

      {/* ── Moment text — "Одно Мгновение до..." ── */}
      <AnimatePresence>
        {phase === "moment" && (
          <motion.div
            key="moment"
            initial={{ opacity: 0, y: 10, filter: "blur(8px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -6, filter: "blur(4px)" }}
            transition={{ duration: 0.6, ease: EASE_SNAP }}
            className="absolute font-mono text-center"
            style={{
              top: "calc(50% - clamp(5rem, 14vw, 10rem) - 2.5rem)",
              color: "var(--text-muted)",
              letterSpacing: "0.32em",
              fontSize: "clamp(0.6rem, 1.5vw, 0.85rem)",
              textTransform: "uppercase",
            }}
          >
            Одно&nbsp;Мгновение&nbsp;до&nbsp;·&nbsp;·&nbsp;·
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Main number ── */}
      <AnimatePresence mode="wait">
        {phase !== "quote" && phase !== "exit" && (
          <motion.div
            key="number"
            initial={{ opacity: 0, scale: 0.92, filter: "blur(10px)" }}
            animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, scale: 1.08, filter: "blur(12px)" }}
            transition={{ duration: 0.4, ease: EASE_SNAP }}
            className="relative font-display font-black tabular-nums text-center select-none"
            style={{
              fontSize: "clamp(3.5rem, 16vw, 12rem)",
              lineHeight: 1,
              color: "transparent",
              WebkitTextStroke: "1.5px var(--accent)",
              filter: "drop-shadow(0 0 40px var(--accent-glow))",
              letterSpacing: "-0.02em",
            }}
          >
            {numStr}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Quote ── */}
      <AnimatePresence>
        {(phase === "quote" || phase === "exit") && (
          <motion.div
            key="quote"
            initial={{ opacity: 0, y: 30, scale: 0.96, filter: "blur(8px)" }}
            animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
            exit={{ opacity: 0, filter: "blur(6px)" }}
            transition={{ duration: 0.7, ease: EASE_SNAP }}
            className="relative z-10 text-center px-8 max-w-2xl mx-auto"
          >
            {/* Accent line — grows in */}
            <motion.div
              className="mx-auto mb-8"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: "clamp(40px, 8vw, 64px)", opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.15, ease: EASE_SNAP }}
              style={{
                height: "2px",
                background: "var(--accent)",
                boxShadow: "0 0 12px var(--accent-glow)",
              }}
            />
            <motion.p
              className="font-display font-bold leading-tight"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2, ease: EASE_SNAP }}
              style={{
                fontSize: "clamp(1.4rem, 4vw, 2.8rem)",
                color: "var(--text-secondary)",
              }}
            >
              {quote.current.text}{" "}
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.5, delay: 0.5 }}
                style={{
                  color: "var(--accent)",
                  textShadow: "0 0 24px var(--accent-glow)",
                }}
              >
                {quote.current.highlight}
              </motion.span>
            </motion.p>

            {/* Brand watermark */}
            <motion.div
              className="mt-10 flex items-center justify-center gap-2"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.7 }}
            >
              <div
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: "var(--accent)", boxShadow: "0 0 8px var(--accent-glow)" }}
              />
              <span
                className="font-mono text-xs tracking-[0.5em] uppercase"
                style={{ color: "var(--text-muted)" }}
              >
                X · Hunter
              </span>
              <div
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: "var(--accent)", boxShadow: "0 0 8px var(--accent-glow)" }}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

    </motion.div>
  );
}
