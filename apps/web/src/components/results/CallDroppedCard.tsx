"use client";

/**
 * CallDroppedCard — Phase C (2026-05-08)
 *
 * Replaces the «ПОТЕРЯЛ КОНТРОЛЬ» PostSessionVerdict for terminal
 * outcomes that are NOT the user's fault — `technical_failed`,
 * `timeout`, `operator_aborted`. Previously these sessions still
 * got a triumphant verdict-word ("LOST CONTROL") with a 0/100
 * score visualisation, framing system errors as user failure.
 *
 * Visual language: dark CRT-glitch card with scanline + brief
 * RGB-shift on mount. Big pixel-font «СВЯЗЬ ОБОРВАНА» message,
 * a subtitle calibrated to the actual outcome reason, and two
 * CTAs: «Перезвонить» (creates a fresh session of the same
 * scenario) and «К тренировкам» (escape hatch).
 *
 * Deliberately reads NOTHING from `score_total` — these sessions
 * have no meaningful score and we don't want to show 0/100.
 */

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { PhoneOff, RefreshCw, ArrowLeft } from "lucide-react";

export type CallDroppedReason =
  | "technical_failed"
  | "timeout"
  | "operator_aborted";

export interface CallDroppedCardProps {
  reason: CallDroppedReason;
  /** Optional human-readable detail (e.g. "Long silence — client tired of waiting"). */
  detail?: string;
  /** Called when user taps «Перезвонить» — parent should create a new session. */
  onRetry?: () => void;
  /** Called when user taps «К тренировкам» — parent should navigate /training. */
  onExit?: () => void;
  /** Called when user taps «Показать что было» — parent expands the transcript replay. */
  onShowTranscript?: () => void;
}

const SUBTITLE_FOR: Record<CallDroppedReason, string> = {
  technical_failed: "Системный сбой. Это не на твоей стороне.",
  timeout: "Длительная тишина. Клиент устал ждать.",
  operator_aborted: "Звонок прерван без диалога.",
};

export default function CallDroppedCard({
  reason,
  detail,
  onRetry,
  onExit,
  onShowTranscript,
}: CallDroppedCardProps) {
  // Brief RGB-shift glitch on first mount, then settles.
  const [glitching, setGlitching] = useState(true);
  useEffect(() => {
    const tid = window.setTimeout(() => setGlitching(false), 600);
    return () => window.clearTimeout(tid);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="relative mx-auto w-full max-w-2xl overflow-hidden rounded-2xl"
      style={{
        background: "linear-gradient(180deg, #0a0a0f 0%, #0d0d14 100%)",
        border: "1px solid rgba(255,255,255,0.08)",
        boxShadow: "0 12px 48px rgba(0,0,0,0.48)",
      }}
      role="status"
      aria-live="polite"
    >
      {/* Animated scanline (subtle, infinite). */}
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 h-[1px]"
        style={{ background: "rgba(255,255,255,0.07)" }}
        initial={{ y: "0%" }}
        animate={{ y: "100%" }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "linear" }}
      />

      <div className="px-8 pb-8 pt-10 text-center">
        {/* PhoneOff icon with red glow */}
        <motion.div
          aria-hidden
          className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full"
          style={{
            background: "rgba(229,72,77,0.12)",
            border: "1.5px solid rgba(229,72,77,0.45)",
            boxShadow: "0 0 32px rgba(229,72,77,0.25)",
          }}
          animate={{ scale: [1, 1.04, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
        >
          <PhoneOff size={28} style={{ color: "rgba(255,140,140,0.95)" }} />
        </motion.div>

        {/* Pixel-font headline with RGB-shift on mount */}
        <div className="relative mx-auto mb-3 inline-block" style={{ letterSpacing: "0.08em" }}>
          {/* Cyan ghost (left shift) */}
          {glitching && (
            <motion.div
              aria-hidden
              initial={{ x: 0, opacity: 0.85 }}
              animate={{ x: -2, opacity: 0 }}
              transition={{ duration: 0.6, ease: "easeOut" }}
              className="absolute inset-0 font-display text-4xl font-bold md:text-5xl"
              style={{ color: "rgba(80,220,255,0.7)", mixBlendMode: "screen" }}
            >
              СВЯЗЬ ОБОРВАНА
            </motion.div>
          )}
          {/* Magenta ghost (right shift) */}
          {glitching && (
            <motion.div
              aria-hidden
              initial={{ x: 0, opacity: 0.85 }}
              animate={{ x: 2, opacity: 0 }}
              transition={{ duration: 0.6, ease: "easeOut" }}
              className="absolute inset-0 font-display text-4xl font-bold md:text-5xl"
              style={{ color: "rgba(255,80,200,0.7)", mixBlendMode: "screen" }}
            >
              СВЯЗЬ ОБОРВАНА
            </motion.div>
          )}
          <h2
            className="relative font-display text-4xl font-bold md:text-5xl"
            style={{ color: "rgba(255,255,255,0.96)" }}
          >
            СВЯЗЬ ОБОРВАНА
          </h2>
        </div>

        <p className="mt-3 text-sm md:text-base" style={{ color: "rgba(255,255,255,0.66)" }}>
          {SUBTITLE_FOR[reason]}
        </p>

        {detail && (
          <p
            className="mx-auto mt-2 max-w-md text-xs"
            style={{ color: "rgba(255,255,255,0.42)" }}
          >
            {detail}
          </p>
        )}

        {/* Reason chip */}
        <div className="mt-4 inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[10px] font-mono uppercase tracking-wider"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            color: "rgba(255,255,255,0.5)",
          }}
        >
          <span style={{ color: "rgba(229,72,77,0.85)" }}>●</span>
          {reason.replace(/_/g, " ")}
        </div>

        {/* CTAs */}
        <div className="mt-7 flex flex-col items-center justify-center gap-3 sm:flex-row">
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition-transform hover:scale-[1.02]"
              style={{
                background: "linear-gradient(135deg, rgba(61,220,132,0.95), rgba(40,175,100,0.95))",
                color: "#062a13",
                boxShadow: "0 6px 24px rgba(61,220,132,0.25)",
              }}
            >
              <RefreshCw size={16} />
              Перезвонить
            </button>
          )}
          {onExit && (
            <button
              type="button"
              onClick={onExit}
              className="inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition-transform hover:scale-[1.02]"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.12)",
                color: "rgba(255,255,255,0.85)",
              }}
            >
              <ArrowLeft size={16} />К тренировкам
            </button>
          )}
        </div>

        {/* Optional transcript link */}
        {onShowTranscript && (
          <button
            type="button"
            onClick={onShowTranscript}
            className="mt-5 text-[11px] underline-offset-2 hover:underline"
            style={{ color: "rgba(255,255,255,0.4)" }}
          >
            Показать что было
          </button>
        )}
      </div>

      {/* Bottom CRT vignette */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-12"
        style={{
          background: "linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.5) 100%)",
        }}
      />
    </motion.div>
  );
}
