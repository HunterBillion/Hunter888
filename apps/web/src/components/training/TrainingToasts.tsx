"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  PhoneOff,
  Lightbulb,
  CheckCircle2,
  AlertTriangle,
  Clock,
} from "lucide-react";
import type { ObjectionHint, CheckpointHint } from "@/types";

interface TrainingToastsProps {
  hangupWarning: string | null;
  objectionHint: ObjectionHint | null;
  checkpointHint: CheckpointHint | null;
  silenceWarning: boolean;
  elapsed: number;
  sessionState: string;
  formatTime: (seconds: number) => string;
}

export function TrainingToasts({
  hangupWarning,
  objectionHint,
  checkpointHint,
  silenceWarning,
  elapsed,
  sessionState,
  formatTime,
}: TrainingToastsProps) {
  return (
    <>
      {/* ── Hangup Warning Toast ─────────────────────────── */}
      <AnimatePresence>
        {hangupWarning && (
          <motion.div
            initial={{ opacity: 0, y: -30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            className="fixed top-20 left-1/2 -translate-x-1/2 z-[140] max-w-sm rounded-xl px-5 py-3"
            style={{
              background: "rgba(255,51,51,0.12)",
              border: "1px solid rgba(255,51,51,0.35)",
              backdropFilter: "blur(16px)",
              boxShadow: "0 0 20px rgba(255,51,51,0.15)",
            }}
          >
            <div className="flex items-center gap-3">
              <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center" style={{ background: "rgba(255,51,51,0.2)" }}>
                <PhoneOff size={14} style={{ color: "var(--neon-red)" }} />
              </div>
              <div>
                <div className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--neon-red)" }}>
                  КЛИЕНТ ТЕРЯЕТ ТЕРПЕНИЕ
                </div>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-secondary)" }}>
                  {hangupWarning}
                </p>
              </div>
            </div>
            {/* Auto-dismiss progress bar */}
            <motion.div
              className="mt-2 h-0.5 rounded-full"
              style={{ background: "rgba(255,51,51,0.4)" }}
              initial={{ width: "100%" }}
              animate={{ width: "0%" }}
              transition={{ duration: 5, ease: "linear" }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Objection Hint Toast ──────────────────────────── */}
      <AnimatePresence>
        {objectionHint && (
          <motion.div
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            className="fixed top-16 left-1/2 -translate-x-1/2 z-[160] w-[90vw] max-w-sm"
          >
            <div
              className="rounded-2xl p-4 backdrop-blur-xl flex items-start gap-3"
              style={{
                background: "rgba(99,102,241,0.12)",
                border: "1px solid rgba(99,102,241,0.35)",
                boxShadow: "0 8px 32px rgba(99,102,241,0.2)",
              }}
            >
              <div className="flex items-center justify-center w-8 h-8 rounded-lg shrink-0" style={{ background: "rgba(99,102,241,0.2)" }}>
                <Lightbulb size={16} style={{ color: "var(--accent)" }} />
              </div>
              <div>
                <div className="font-mono text-xs tracking-widest uppercase font-semibold" style={{ color: "var(--accent)" }}>
                  Подсказка
                </div>
                <div className="text-sm mt-1 leading-relaxed" style={{ color: "var(--text-primary)" }}>
                  {objectionHint.message}
                </div>
              </div>
            </div>
            {/* Auto-dismiss progress bar */}
            <motion.div
              className="mt-1 mx-4 h-0.5 rounded-full"
              style={{ background: "rgba(99,102,241,0.4)" }}
              initial={{ width: "100%" }}
              animate={{ width: "0%" }}
              transition={{ duration: 4, ease: "linear" }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Checkpoint Hint Toast ─────────────────────────── */}
      <AnimatePresence>
        {checkpointHint && (
          <motion.div
            initial={{ opacity: 0, y: -20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            className="fixed top-16 left-1/2 -translate-x-1/2 z-[140]"
          >
            <div
              className="rounded-xl px-5 py-3 backdrop-blur-xl flex items-center gap-3"
              style={{
                background: "rgba(0,255,148,0.08)",
                border: "1px solid rgba(0,255,148,0.25)",
                boxShadow: "0 4px 20px rgba(0,255,148,0.12)",
              }}
            >
              <CheckCircle2 size={16} style={{ color: "var(--neon-green, #00FF94)" }} />
              <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
                Сейчас хорошо бы: <span className="font-semibold" style={{ color: "var(--neon-green, #00FF94)" }}>{checkpointHint.checkpoint}</span>
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Silence Warning Banner ──────────────────────────── */}
      <AnimatePresence>
        {silenceWarning && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[140] flex items-center gap-3 rounded-xl px-5 py-3"
            style={{
              background: "rgba(245,158,11,0.15)",
              border: "1px solid rgba(245,158,11,0.3)",
              backdropFilter: "blur(12px)",
              boxShadow: "0 0 20px rgba(245,158,11,0.15)",
            }}
          >
            <AlertTriangle size={18} style={{ color: "var(--warning)" }} />
            <span className="font-mono text-sm" style={{ color: "var(--warning)" }}>
              Вы молчите — скоро сессия будет приостановлена
            </span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Timer Warning (25min+) ────────────────────────── */}
      <AnimatePresence>
        {elapsed >= 1500 && elapsed < 1800 && sessionState === "ready" && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed top-20 right-6 z-[130] flex items-center gap-2 rounded-xl px-4 py-2"
            style={{
              background: "rgba(245,158,11,0.1)",
              border: "1px solid rgba(245,158,11,0.2)",
              backdropFilter: "blur(12px)",
            }}
          >
            <Clock size={14} style={{ color: "var(--warning)" }} />
            <span className="font-mono text-xs" style={{ color: "var(--warning)" }}>
              {formatTime(1800 - elapsed)} до лимита
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
