"use client";

/**
 * CallDialingOverlay (2026-05-01, Phase 1 of the call-flow lifecycle redesign)
 *
 * Renders a full-screen "Соединение..." overlay for ~1.2 seconds between
 * the user clicking «Принять звонок» on IncomingCallScreen and the
 * PhoneCallMode active-call UI taking over. Plays a short Russian-style
 * outgoing dial tone via the Web Audio API (no asset file needed).
 *
 * Why this exists
 * ───────────────
 * Pre-redesign UX: click Accept → instantly hear AI say "Алло?". Felt
 * AI-y because real phone calls have a connecting / ringing phase
 * between dialing and answer. This overlay supplies that micro-pause
 * with realistic visual + audio cues. The 1.2s duration is short enough
 * not to feel like artificial latency but long enough for the brain to
 * register "I'm calling someone".
 *
 * Audio
 * ─────
 * Russian outgoing dial tone is a 425 Hz tone, 1 s on / 4 s off pattern.
 * We play one beep (1.0 s on then quick fade) — enough to set the
 * expectation without forcing the user to wait through the full silence
 * cycle. Volume is low (-12 dB equivalent) and uses the same gesture
 * unlock that the parent already executed.
 *
 * Visuals
 * ───────
 * - Animated phone icon (pulsing, slow rotation)
 * - Status text cycles: "Соединение..." → "Гудки идут..."
 * - Subtle scanline effect to evoke an actual line connecting
 * - Background uses the same scene gradient as PhoneCallMode so the
 *   transition out is a crossfade rather than a jump-cut
 */

import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Phone } from "lucide-react";

export interface CallDialingOverlayProps {
  /** When true, overlay is rendered. Parent should keep this true for
   *  ~1200ms then flip to false; the AnimatePresence inside handles
   *  the fade-out transition. */
  visible: boolean;
  /** Optional name to show under the phone icon, e.g. "Иван Петрович". */
  calleeName?: string;
}

/** Play a single Russian-style dial-tone beep (425 Hz, ~900ms with fades). */
function playDialTone(): { stop: () => void } {
  if (typeof window === "undefined") return { stop: () => {} };
  try {
    const AC = (window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext) as typeof AudioContext | undefined;
    if (!AC) return { stop: () => {} };
    const ctx = new AC();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 425; // Russian PTSN dial-tone frequency
    // Soft attack + sustain + release envelope
    const now = ctx.currentTime;
    gain.gain.setValueAtTime(0, now);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.05);
    gain.gain.setValueAtTime(0.18, now + 0.85);
    gain.gain.linearRampToValueAtTime(0, now + 0.95);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now);
    osc.stop(now + 1.0);
    let stopped = false;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      try { osc.stop(); } catch { /* already stopped */ }
      try { ctx.close(); } catch { /* */ }
    };
    setTimeout(stop, 1200);
    return { stop };
  } catch {
    return { stop: () => {} };
  }
}

export default function CallDialingOverlay({
  visible,
  calleeName,
}: CallDialingOverlayProps) {
  const stopperRef = useRef<{ stop: () => void } | null>(null);

  useEffect(() => {
    if (visible) {
      stopperRef.current = playDialTone();
      return () => {
        try { stopperRef.current?.stop(); } catch { /* */ }
      };
    }
  }, [visible]);

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="dialing-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-gradient-to-b from-black/95 via-zinc-950/95 to-black/95 backdrop-blur-md"
          aria-live="polite"
          aria-label="Соединение"
        >
          {/* Pulsing concentric rings around the phone icon */}
          <div className="relative flex h-44 w-44 items-center justify-center">
            <motion.span
              className="absolute h-full w-full rounded-full bg-emerald-500/15 ring-1 ring-emerald-400/30"
              animate={{ scale: [1, 1.6, 1.6], opacity: [0.6, 0, 0] }}
              transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
            />
            <motion.span
              className="absolute h-full w-full rounded-full bg-emerald-500/10 ring-1 ring-emerald-400/20"
              animate={{ scale: [1, 1.8, 1.8], opacity: [0.5, 0, 0] }}
              transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut", delay: 0.4 }}
            />
            <motion.div
              className="relative flex h-24 w-24 items-center justify-center rounded-full bg-emerald-500/20 ring-2 ring-emerald-300/60"
              animate={{
                rotate: [0, -8, 8, -4, 4, 0],
                scale: [1, 1.05, 1, 1.05, 1],
              }}
              transition={{
                duration: 1.4,
                repeat: Infinity,
                ease: "easeInOut",
              }}
            >
              <Phone className="h-10 w-10 text-emerald-200" strokeWidth={2.2} />
            </motion.div>
          </div>

          {/* Status text */}
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.3 }}
            className="mt-8 flex flex-col items-center gap-1"
          >
            {calleeName && (
              <div className="text-2xl font-semibold tracking-tight text-white">
                {calleeName}
              </div>
            )}
            <DialingStatusText />
          </motion.div>

          {/* Scanline effect — subtle, suggests a line being established */}
          <motion.div
            aria-hidden
            className="pointer-events-none absolute inset-x-0 h-[1px] bg-emerald-300/20"
            initial={{ y: "0%" }}
            animate={{ y: "100%" }}
            transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Cycles "Соединение..." → "Гудки идут..." every ~600ms. */
function DialingStatusText() {
  const messages = ["Соединение", "Гудки идут"];
  return (
    <div className="text-sm uppercase tracking-[0.2em] text-emerald-300/80">
      <motion.span
        animate={{ opacity: [0.6, 1, 0.6] }}
        transition={{ duration: 1.6, repeat: Infinity }}
      >
        <CycleText messages={messages} intervalMs={700} />
        <motion.span
          animate={{ opacity: [0, 1, 0] }}
          transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
        >
          ...
        </motion.span>
      </motion.span>
    </div>
  );
}

import { useState } from "react";
function CycleText({ messages, intervalMs }: { messages: string[]; intervalMs: number }) {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setIdx((i) => (i + 1) % messages.length), intervalMs);
    return () => clearInterval(t);
  }, [messages.length, intervalMs]);
  return <span>{messages[idx]}</span>;
}
