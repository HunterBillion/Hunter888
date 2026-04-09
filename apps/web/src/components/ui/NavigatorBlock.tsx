"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { getClientNavigator, TOTAL_QUOTES } from "@/lib/navigator-quotes";
import { CompassIcon } from "./CompassIcon";
import { logger } from "@/lib/logger";
import { EASE_SNAP } from "@/lib/constants";

/* ── Types matching GET /navigator/current ─────────────────────────────────── */
interface NavigatorData {
  index:             number;
  total:             number;
  text:              string;
  author:            string;
  source:            string;
  category:          string;
  category_label:    string;
  slot:              number;        // 0–3
  next_change_at:    string;        // ISO UTC
  seconds_remaining: number;
}

/* ── Slot colour definitions (RGB base) ─────────────────────────────────────── */
// Using raw RGB so we can construct rgba(..., alpha) reliably
// instead of broken hex-suffix patterns like `rgba(...)12`
interface SlotColor {
  rgb: string;      // e.g. "251,191,36"
  solid: string;    // e.g. "rgba(251,191,36,0.9)" — for text, needle
  cssVar?: string;  // if using CSS var for solid
}

const SLOT_COLORS: SlotColor[] = [
  { rgb: "144,92,237",  solid: "var(--accent)", cssVar: "var(--accent)" },   // slot 0 — night → purple
  { rgb: "251,191,36",  solid: "rgba(251,191,36,0.9)" },                     // slot 1 — morning → amber
  { rgb: "99,202,183",  solid: "rgba(99,202,183,0.9)" },                     // slot 2 — afternoon → teal
  { rgb: "167,139,250", solid: "rgba(167,139,250,0.9)" },                    // slot 3 — evening → violet
];

/** Generate rgba color with specific opacity */
function withAlpha(rgb: string, alpha: number): string {
  return `rgba(${rgb},${alpha})`;
}

function formatCountdown(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}ч ${m.toString().padStart(2, "0")}м`;
  if (m > 0) return `${m}м ${s.toString().padStart(2, "0")}с`;
  return `${s}с`;
}

/** Build NavigatorData from client-side computation */
function buildClientData(): NavigatorData {
  const { quote, index, slot, secondsRemaining } = getClientNavigator();
  const nextSlotH = (slot + 1) * 6;
  const nextSlot = new Date();
  nextSlot.setUTCMinutes(0, 0, 0);
  if (nextSlotH < 24) {
    nextSlot.setUTCHours(nextSlotH);
  } else {
    nextSlot.setUTCDate(nextSlot.getUTCDate() + 1);
    nextSlot.setUTCHours(0);
  }
  return {
    index,
    total: TOTAL_QUOTES,
    text: quote.text,
    author: quote.author,
    source: quote.source,
    category: quote.category,
    category_label: quote.category_label,
    slot,
    next_change_at: nextSlot.toISOString(),
    seconds_remaining: secondsRemaining,
  };
}

/* ─────────────────────────────── Component ────────────────────────────────── */
export function NavigatorBlock() {
  const [data, setData]       = useState<NavigatorData | null>(null);
  const [mounted, setMounted] = useState(false);
  const [visible, setVisible] = useState(true);
  const [countdown, setCountdown] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── On mount: compute client-side immediately, then try API ── */
  useEffect(() => {
    const clientData = buildClientData();
    setData(clientData);
    setCountdown(clientData.seconds_remaining);
    setMounted(true);

    // Try API in background for potential enrichment
    api.get("/navigator/current")
      .then((d: NavigatorData) => {
        if (d.index !== clientData.index) {
          setVisible(false);
          setTimeout(() => {
            setData(d);
            setCountdown(d.seconds_remaining);
            setVisible(true);
          }, 350);
        } else {
          setCountdown(d.seconds_remaining);
        }
      })
      .catch((err) => {
        logger.warn("Navigator sync failed, staying on client data:", err);
      });

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  /* ── Countdown ticker ── */
  useEffect(() => {
    if (!data) return;
    if (intervalRef.current) clearInterval(intervalRef.current);

    intervalRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(intervalRef.current!);
          const newData = buildClientData();
          setVisible(false);
          setTimeout(() => {
            setData(newData);
            setCountdown(newData.seconds_remaining);
            setVisible(true);
          }, 350);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [data?.index]);

  /* ── Derive color values ── */
  const slotColor = data ? (SLOT_COLORS[data.slot] ?? SLOT_COLORS[0]) : SLOT_COLORS[0];
  const accent = slotColor.solid;
  const rgb = slotColor.rgb;

  /* ── SSR skeleton ── */
  if (!mounted || !data) {
    return (
      <div
        className="rounded-2xl p-5 sm:p-6 flex items-start gap-4"
        style={{
          background: "linear-gradient(135deg, rgba(124,106,232,0.07), rgba(124,106,232,0.02))",
          border: "1px solid rgba(124,106,232,0.18)",
        }}
      >
        <div className="w-12 sm:w-14 h-12 sm:h-14 rounded-full skeleton-neon shrink-0" />
        <div className="flex-1 space-y-2.5 py-1">
          <div className="h-2.5 w-24 rounded-full skeleton-neon" />
          <div className="h-5 w-4/5 rounded-lg skeleton-neon" />
          <div className="h-5 w-3/5 rounded-lg skeleton-neon" />
          <div className="h-3 w-32 rounded-full skeleton-neon" />
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE_SNAP }}
      className="relative rounded-2xl overflow-hidden glass-panel-glow"
      style={{
        background: `linear-gradient(135deg, ${withAlpha(rgb, 0.07)} 0%, ${withAlpha(rgb, 0.025)} 60%, transparent 100%)`,
        border: `1px solid ${withAlpha(rgb, 0.18)}`,
      }}
    >
      {/* Subtle corner glow */}
      <div
        className="absolute -top-12 -right-12 w-36 sm:w-48 h-36 sm:h-48 rounded-full pointer-events-none"
        style={{ background: `radial-gradient(circle, ${withAlpha(rgb, 0.1)} 0%, transparent 70%)` }}
      />

      <div className="relative z-10 p-4 sm:p-5 md:p-6">
        {/* ── Header row ── */}
        <div className="flex items-center gap-3 sm:gap-4 mb-3 sm:mb-4">

          {/* Compass */}
          <CompassIcon
            size={48}
            accentColor={accent}
            accentRgb={rgb}
            oscillate={true}
          />

          {/* Title + category + countdown */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className="font-mono text-xs uppercase tracking-[0.38em] font-bold"
                style={{ color: accent }}
              >
                НАВИГАТОР
              </span>
              <span
                className="font-mono text-[7px] sm:text-xs px-1.5 sm:px-2 py-0.5 rounded-full tracking-wider uppercase truncate max-w-[140px] sm:max-w-none"
                style={{
                  background: withAlpha(rgb, 0.1),
                  border: `1px solid ${withAlpha(rgb, 0.15)}`,
                  color: accent,
                  opacity: 0.85,
                }}
              >
                {data.category_label}
              </span>
            </div>
            {/* Countdown */}
            <div className="mt-1 flex items-center gap-1.5">
              <div
                className="w-1 h-1 rounded-full animate-pulse"
                style={{ background: accent }}
              />
              <span
                className="font-mono text-xs tracking-wider"
                style={{ color: "var(--text-muted)", opacity: 0.7 }}
              >
                Обновление через {formatCountdown(countdown)}
              </span>
            </div>
          </div>
        </div>

        {/* ── Quote text ── */}
        <AnimatePresence mode="wait">
          {visible && (
            <motion.div
              key={data.index}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.35, ease: EASE_SNAP }}
            >
              {/* Accent line */}
              <div
                className="mb-2.5 sm:mb-3"
                style={{
                  width: 32,
                  height: 2,
                  background: accent,
                  borderRadius: 2,
                  boxShadow: `0 0 8px ${withAlpha(rgb, 0.5)}`,
                }}
              />

              <blockquote
                className="font-display font-semibold leading-snug"
                style={{
                  fontSize: "clamp(0.95rem, 2.5vw, 1.22rem)",
                  color: "var(--text-primary)",
                  lineHeight: 1.55,
                }}
              >
                «{data.text}»
              </blockquote>

              {/* Author + source */}
              <div className="mt-2.5 sm:mt-3 flex items-center gap-2">
                <div
                  className="w-5 sm:w-6 h-[1px] shrink-0"
                  style={{ background: withAlpha(rgb, 0.35) }}
                />
                <p
                  className="font-mono text-xs sm:text-xs tracking-wide truncate"
                  style={{ color: "var(--text-muted)" }}
                >
                  {data.author}
                  {data.source && (
                    <span style={{ opacity: 0.6 }}>, «{data.source}»</span>
                  )}
                </p>
              </div>

              {/* Progress indicator: quote N of TOTAL */}
              <div className="mt-3 sm:mt-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs tracking-wider" style={{ color: "var(--text-muted)", opacity: 0.5 }}>
                    {data.index + 1} / {data.total}
                  </span>
                  <span className="font-mono text-xs tracking-wider" style={{ color: accent, opacity: 0.6 }}>
                    СЛОТ {data.slot + 1}/4
                  </span>
                </div>
                <div
                  className="h-[2px] w-full rounded-full overflow-hidden"
                  style={{ background: withAlpha(rgb, 0.1) }}
                >
                  <motion.div
                    className="h-full rounded-full"
                    style={{ background: accent }}
                    initial={{ width: 0 }}
                    animate={{ width: `${((data.index + 1) / data.total) * 100}%` }}
                    transition={{ duration: 0.8, ease: EASE_SNAP }}
                  />
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
