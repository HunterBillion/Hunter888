"use client";

/**
 * CallEndingTransition (2026-05-01, Phase 5+6 of the call-flow lifecycle redesign)
 *
 * Replaces the previously static "📞 Звонок завершён / Сохраняем результаты..."
 * screen with a rich animated transition between hangup and the /results
 * page. Sells the "I just hung up an actual phone call" feeling and
 * gives the user a moment to register what just happened.
 *
 * Visual flow over ~2.2 seconds:
 *   t=0.0s  end-call icon + "Звонок завершён"
 *   t=0.6s  "Анализирую разговор..."
 *   t=1.2s  "Считаю баллы..."
 *   t=1.8s  "Готовлю отчёт..."
 *   t=2.2s  parent triggers router.replace → /results
 *
 * Audio
 * ─────
 * Single soft hangup-click tone via Web Audio (300 Hz, ~150ms) right at
 * mount — gives the brain a "the line just dropped" cue.
 *
 * Accessibility
 * ─────────────
 * aria-live=polite + label so screen readers announce "Звонок завершён"
 * exactly once, not on each status-text rotation.
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PhoneOff, Sparkles, Award, FileText } from "lucide-react";

export interface CallEndingTransitionProps {
  /** Optional reason text passed by parent (e.g. "вы попрощались",
   *  "клиент бросил трубку"). Shown beneath the status. */
  reason?: string;
  /** Optional final stats to tease before /results loads. Each pair is
   *  rendered as "Label: value" in a compact chip row. */
  stats?: Array<{ label: string; value: string }>;
}

const STATUS_FRAMES: Array<{
  icon: typeof PhoneOff;
  text: string;
  /** ms after mount this frame becomes active. */
  showAt: number;
}> = [
  { icon: PhoneOff, text: "Звонок завершён", showAt: 0 },
  { icon: Sparkles, text: "Анализирую разговор", showAt: 600 },
  { icon: Award, text: "Считаю баллы", showAt: 1200 },
  { icon: FileText, text: "Готовлю отчёт", showAt: 1800 },
];

/** Single soft hangup-click tone — "line dropped" cue. */
function playHangupClick(): void {
  if (typeof window === "undefined") return;
  try {
    const AC = (window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext) as typeof AudioContext | undefined;
    if (!AC) return;
    const ctx = new AC();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 300;
    const now = ctx.currentTime;
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 0.18);
    setTimeout(() => { try { ctx.close(); } catch { /* */ } }, 250);
  } catch {
    /* ignore */
  }
}

export default function CallEndingTransition({
  reason,
  stats,
}: CallEndingTransitionProps) {
  const [activeFrameIdx, setActiveFrameIdx] = useState(0);

  useEffect(() => {
    playHangupClick();
    const timers: ReturnType<typeof setTimeout>[] = [];
    STATUS_FRAMES.forEach((frame, idx) => {
      if (idx === 0) return;
      timers.push(setTimeout(() => setActiveFrameIdx(idx), frame.showAt));
    });
    return () => timers.forEach((t) => clearTimeout(t));
  }, []);

  const Frame = STATUS_FRAMES[activeFrameIdx];
  const Icon = Frame.icon;

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-6 text-white"
      style={{
        background:
          "radial-gradient(ellipse at center, #2a1a4a 0%, #14091e 55%, #06030c 100%)",
      }}
      role="status"
      aria-live="polite"
      aria-label="Звонок завершён, готовим результаты"
    >
      {/* Animated end-call icon — pulsing red/orange ring */}
      <div className="relative flex h-32 w-32 items-center justify-center">
        <motion.span
          className="absolute h-full w-full rounded-full bg-rose-500/15 ring-1 ring-rose-400/30"
          animate={{ scale: [1, 1.4, 1.4], opacity: [0.6, 0, 0] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
        />
        <motion.div
          className="relative flex h-20 w-20 items-center justify-center rounded-full bg-rose-500/20 ring-2 ring-rose-300/60"
          animate={{ scale: [1, 1.04, 1] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={activeFrameIdx}
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.7 }}
              transition={{ duration: 0.25 }}
            >
              <Icon className="h-9 w-9 text-rose-100" strokeWidth={2} />
            </motion.div>
          </AnimatePresence>
        </motion.div>
      </div>

      {/* Status text */}
      <div className="flex flex-col items-center gap-2">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeFrameIdx}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.25 }}
            className="text-xl font-semibold tracking-tight"
          >
            {Frame.text}
          </motion.div>
        </AnimatePresence>
        {reason && (
          <div className="max-w-sm px-8 text-center text-sm text-white/60">
            {reason}
          </div>
        )}
      </div>

      {/* Stats teaser */}
      {stats && stats.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.4 }}
          className="flex flex-wrap justify-center gap-2 px-6"
        >
          {stats.map((s) => (
            <div
              key={s.label}
              className="rounded-full bg-white/5 px-3 py-1.5 text-xs ring-1 ring-white/10 backdrop-blur-sm"
            >
              <span className="text-white/50">{s.label}:</span>{" "}
              <span className="font-medium text-white/90">{s.value}</span>
            </div>
          ))}
        </motion.div>
      )}

      {/* Progress bar — fills over 2.2s */}
      <div className="mt-2 h-[3px] w-56 overflow-hidden rounded-full bg-white/10">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-rose-400 via-fuchsia-400 to-violet-400"
          initial={{ width: "0%" }}
          animate={{ width: "100%" }}
          transition={{ duration: 2.2, ease: "easeInOut" }}
        />
      </div>
    </div>
  );
}
