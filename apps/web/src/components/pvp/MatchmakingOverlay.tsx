"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Search, Swords, Loader2, X, Shield, Zap } from "lucide-react";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface Props {
  status: "searching" | "matched";
  position: number;
  estimatedWait: number;
  opponentRating?: number;
  onCancel: () => void;
}

const MATCH_TIMEOUT = 90;

const TIPS = [
  "Первые 10 дуэлей — калибровочные. Рейтинг определяется быстрее.",
  "В Round 2 роли меняются: менеджер становится клиентом и наоборот.",
  "AI-судья оценивает: возражения, убеждение, структуру и юр. точность.",
  "Чем точнее вы цитируете ФЗ-127, тем выше балл за юридическую точность.",
  "Лимит — 8 сообщений за раунд. Будьте лаконичны и убедительны.",
  "PvE-дуэли дают 50% рейтинговых очков. Живой соперник — полный рейтинг.",
];

export function MatchmakingOverlay({ status, position, estimatedWait, opponentRating, onCancel }: Props) {
  const reducedMotion = useReducedMotion();
  const rem = estimatedWait > 0 ? estimatedWait : MATCH_TIMEOUT;
  const [anchor, setAnchor] = useState({ remaining: rem, wait: MATCH_TIMEOUT - rem, ts: Date.now() });
  const [live, setLive] = useState({ remaining: rem, wait: Math.max(0, MATCH_TIMEOUT - rem) });
  const [tipIndex, setTipIndex] = useState(0);

  // Set anchor ONCE when search starts — don't reset on estimatedWait changes
  const searchStartedRef = useRef(false);
  useEffect(() => {
    if (status !== "searching") {
      searchStartedRef.current = false;
      return;
    }
    if (searchStartedRef.current) return;
    searchStartedRef.current = true;
    const r = estimatedWait > 0 ? estimatedWait : MATCH_TIMEOUT;
    const w = Math.max(0, MATCH_TIMEOUT - r);
    setAnchor({ remaining: r, wait: w, ts: Date.now() });
    setLive({ remaining: r, wait: w });
  }, [status, estimatedWait]);

  useEffect(() => {
    if (status !== "searching") return;
    const tick = () => {
      const elapsed = Math.floor((Date.now() - anchor.ts) / 1000);
      setLive({
        remaining: Math.max(0, anchor.remaining - elapsed),
        wait: anchor.wait + elapsed,
      });
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [status, anchor.remaining, anchor.wait, anchor.ts]);

  // Rotate tips every 8 seconds
  useEffect(() => {
    if (status !== "searching") return;
    const id = setInterval(() => setTipIndex((i) => (i + 1) % TIPS.length), 8000);
    return () => clearInterval(id);
  }, [status]);

  const displayWait = status === "searching" ? live.wait : 0;
  const progress = Math.min(100, Math.round((displayWait / MATCH_TIMEOUT) * 100));
  const isLate = displayWait > 60;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[150] flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.88)", backdropFilter: "blur(8px)" }}
    >
      <motion.div
        initial={{ scale: 0.92, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", damping: 20, stiffness: 300 }}
        className="glass-panel max-w-md w-full mx-4 p-8 text-center"
      >
        {status === "searching" ? (
          <>
            {/* Radar-style search animation */}
            <div className="relative mx-auto w-28 h-28 mb-6">
              {/* Outer ring */}
              <motion.div
                className="absolute inset-0 rounded-full border-2 border-dashed"
                style={{ borderColor: isLate ? "var(--warning)" : "var(--accent)" }}
                animate={reducedMotion ? {} : { rotate: 360 }}
                transition={reducedMotion ? {} : { duration: 3, repeat: Infinity, ease: "linear" }}
              />
              {/* Inner ring */}
              <motion.div
                className="absolute inset-3 rounded-full border"
                style={{ borderColor: isLate ? "rgba(255,215,0,0.2)" : "rgba(99,102,241,0.2)" }}
                animate={reducedMotion ? {} : { rotate: -360 }}
                transition={reducedMotion ? {} : { duration: 5, repeat: Infinity, ease: "linear" }}
              />
              {/* Pulse ring expanding */}
              <motion.div
                className="absolute inset-0 rounded-full"
                style={{ border: `1px solid ${isLate ? "rgba(255,215,0,0.3)" : "rgba(99,102,241,0.3)"}` }}
                animate={reducedMotion ? {} : { scale: [1, 1.3], opacity: [0.6, 0] }}
                transition={reducedMotion ? {} : { duration: 2, repeat: Infinity, ease: "easeOut" }}
              />
              {/* Center icon */}
              <div className="absolute inset-0 flex items-center justify-center">
                <Search size={28} style={{ color: isLate ? "var(--warning)" : "var(--accent)" }} />
              </div>
            </div>

            <h2 className="font-display text-xl font-bold tracking-wide" style={{ color: "var(--text-primary)" }}>
              ИЩЕМ СОПЕРНИКА
            </h2>

            {/* Timer + progress */}
            <div className="mt-4 space-y-3">
              <div className="flex items-end justify-center gap-2 font-mono">
                <span
                  className="text-4xl font-bold tabular-nums transition-colors duration-300"
                  style={{ color: isLate ? "var(--warning)" : "var(--accent)" }}
                >
                  {displayWait}
                </span>
                <span className="pb-1 text-xs" style={{ color: "var(--text-muted)" }}>сек</span>
              </div>

              {/* Progress bar */}
              <div className="mx-auto h-1.5 w-full overflow-hidden rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
                <motion.div
                  className="h-full rounded-full"
                  style={{
                    background: isLate
                      ? "linear-gradient(90deg, var(--accent), var(--warning))"
                      : "linear-gradient(90deg, var(--accent), #7C3AED)",
                  }}
                  animate={{ width: `${progress}%` }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                />
              </div>

              {/* Queue info */}
              {position > 0 && (
                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  В очереди: {position}
                </p>
              )}

              {/* Late warning */}
              {isLate && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-xs font-mono"
                  style={{ color: "var(--warning)" }}
                >
                  Готовим PvE-соперника...
                </motion.p>
              )}
            </div>

            {/* Rotating tips */}
            <div className="mt-5 min-h-[40px] flex items-center justify-center">
              <motion.div
                key={tipIndex}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="flex items-start gap-2 max-w-xs"
              >
                <Zap size={12} className="mt-0.5 shrink-0" style={{ color: "var(--accent)" }} />
                <p className="text-xs leading-relaxed text-left" style={{ color: "var(--text-muted)" }}>
                  {TIPS[tipIndex]}
                </p>
              </motion.div>
            </div>

            <motion.button
              onClick={onCancel}
              className="mt-5 btn-neon flex items-center gap-2 mx-auto text-sm"
              whileTap={{ scale: 0.97 }}
            >
              <X size={14} /> Отмена
            </motion.button>
          </>
        ) : (
          /* ── Match Found: VS Screen ── */
          <>
            {/* Flash effect */}
            <motion.div
              className="fixed inset-0 z-[-1] pointer-events-none"
              initial={{ opacity: 0.5 }}
              animate={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
              style={{ background: "rgba(99,102,241,0.15)" }}
            />

            {/* VS badge */}
            <motion.div
              initial={{ scale: 0, rotate: -45 }}
              animate={{ scale: [0, 1.3, 1], rotate: [-45, 5, 0] }}
              transition={{ duration: 0.6, ease: [0.34, 1.56, 0.64, 1] }}
              className="mx-auto w-20 h-20 rounded-2xl flex items-center justify-center mb-5"
              style={{
                background: "linear-gradient(135deg, rgba(0,255,102,0.12), rgba(99,102,241,0.12))",
                border: "2px solid rgba(0,255,102,0.35)",
                boxShadow: "0 0 30px rgba(0,255,102,0.15)",
              }}
            >
              <Swords size={36} style={{ color: "#00FF66" }} />
            </motion.div>

            <motion.h2
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
              className="font-display text-2xl font-black tracking-wider"
              style={{ color: "#00FF66", textShadow: "0 0 20px rgba(0,255,102,0.25)" }}
            >
              {opponentRating ? "МАТЧ НАЙДЕН" : "АРЕНА ГОТОВА"}
            </motion.h2>

            {/* VS layout */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.5 }}
              className="mt-5 flex items-center justify-center gap-6"
            >
              {/* You */}
              <div className="text-center">
                <div className="w-14 h-14 rounded-xl mx-auto flex items-center justify-center"
                  style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)" }}
                >
                  <Shield size={24} style={{ color: "var(--accent)" }} />
                </div>
                <p className="mt-2 text-xs font-mono font-bold" style={{ color: "var(--text-primary)" }}>ВЫ</p>
              </div>

              {/* VS text */}
              <motion.span
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.6, type: "spring", stiffness: 400, damping: 15 }}
                className="font-display text-lg font-black"
                style={{ color: "var(--text-muted)" }}
              >
                VS
              </motion.span>

              {/* Opponent */}
              <div className="text-center">
                <div className="w-14 h-14 rounded-xl mx-auto flex items-center justify-center"
                  style={{ background: "rgba(255,42,109,0.1)", border: "1px solid rgba(255,42,109,0.25)" }}
                >
                  {opponentRating ? (
                    <Shield size={24} style={{ color: "#FF6B8A" }} />
                  ) : (
                    <span className="text-2xl">&#x1F916;</span>
                  )}
                </div>
                <p className="mt-2 text-xs font-mono font-bold" style={{ color: "var(--text-primary)" }}>
                  {opponentRating ? `${Math.round(opponentRating)}` : "AI"}
                </p>
              </div>
            </motion.div>

            {/* Loading */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8 }}
              className="mt-5 flex items-center justify-center gap-2"
            >
              <Loader2 size={14} className="animate-spin" style={{ color: "var(--accent)" }} />
              <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                Подготовка арены...
              </span>
            </motion.div>
          </>
        )}
      </motion.div>
    </motion.div>
  );
}
