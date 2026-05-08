"use client";

/**
 * SessionEndingOverlay — UNIFIED loader for both call and chat hangup paths.
 *
 * Phase E (2026-05-08): merged with the previous CallEndingTransition
 * component. Pre-merge state had TWO separate overlays:
 *   - CallEndingTransition (call route, 2.2s, phone-themed, 4 frames:
 *     "Звонок завершён → Анализирую → Считаю баллы → Готовлю отчёт")
 *   - SessionEndingOverlay (chat route, ~13s, generic, 4 phases:
 *     "Сохраняем → Считаем → Готовим разбор → XP")
 * Same WS event (`session.ended`), two completely different UX experiences,
 * different copy, different phase counts. Pilot users on call route saw
 * fake-fast 2.2s anim while chat users saw honest 13s backend timeline.
 *
 * Now: ONE component, ONE phase list, mode-driven cosmetics.
 *
 * mode='call' (route /training/[id]/call):
 *   - Phone-themed: PhoneOff icon flash + 300Hz hangup-click on mount
 *   - Shows `reason` (e.g. "клиент бросил трубку") + `stats` chips
 *   - Pulsing rose ring around the icon
 *
 * mode='chat' (route /training/[id]):
 *   - Generic Sparkles icon, no audio cue
 *   - Standard checkmark timeline list, "10–15 секунд" footer
 *
 * Both modes:
 *   - Same 4 phases anchored to real backend pipeline
 *   - Same auto-advance timing (PHASES[i].etaMs)
 *   - Same purple radial gradient background
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Sparkles, PhoneOff } from "lucide-react";

const PHASES: { label: string; etaMs: number }[] = [
  { label: "Сохраняем разговор", etaMs: 600 },
  { label: "Считаем баллы", etaMs: 4500 },
  { label: "Готовим разбор от AI-коуча", etaMs: 7000 },
  { label: "Начисляем достижения и XP", etaMs: 1200 },
  { label: "Готово", etaMs: 0 },
];

export type SessionEndingMode = "call" | "chat";

export interface SessionEndingOverlayProps {
  /** Visibility gate. Both routes pass true when entering ending state. */
  visible: boolean;
  /** Visual flavor. 'call' = phone-themed, 'chat' = generic. Default 'chat'. */
  mode?: SessionEndingMode;
  /** Title at the top. Defaults differ by mode. */
  title?: string;
  /** Subtitle (e.g. character name). Optional. */
  subtitle?: string;
  /** Call-mode only: optional hangup reason (e.g. "клиент бросил трубку"). */
  reason?: string;
  /** Call-mode only: optional stats chips ([{label, value}]). */
  stats?: Array<{ label: string; value: string }>;
}

/** Single soft hangup-click tone — call mode only. */
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

export default function SessionEndingOverlay({
  visible,
  mode = "chat",
  title,
  subtitle,
  reason,
  stats,
}: SessionEndingOverlayProps) {
  const [phaseIdx, setPhaseIdx] = useState(0);
  // Phase G (2026-05-08): show a "это занимает дольше обычного" hint
  // if the overlay is still visible after 20s. Prevents pilots from
  // thinking the app froze when scoring genuinely takes 15-25s.
  const [showSlowHint, setShowSlowHint] = useState(false);

  // Phase auto-advance — same for both modes (honest backend timeline).
  useEffect(() => {
    if (!visible) {
      setPhaseIdx(0);
      setShowSlowHint(false);
      return;
    }
    if (phaseIdx >= PHASES.length - 1) return;
    const eta = PHASES[phaseIdx].etaMs;
    const t = window.setTimeout(
      () => setPhaseIdx((i) => Math.min(i + 1, PHASES.length - 1)),
      eta,
    );
    return () => window.clearTimeout(t);
  }, [visible, phaseIdx]);

  // Phase G: 20s slow-hint timer, independent of phase progression.
  useEffect(() => {
    if (!visible) return;
    const t = window.setTimeout(() => setShowSlowHint(true), 20000);
    return () => window.clearTimeout(t);
  }, [visible]);

  // Call-mode hangup-click on mount.
  useEffect(() => {
    if (visible && mode === "call") {
      playHangupClick();
    }
  }, [visible, mode]);

  // Mode-driven defaults that don't fit nicely into prop defaults.
  const effectiveTitle =
    title ?? (mode === "call" ? "Звонок завершён" : "Завершаем тренировку");

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          key="session-ending"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="fixed inset-0 z-[110] flex flex-col items-center justify-center text-white"
          style={{
            background:
              "radial-gradient(ellipse at center, #2a1a4a 0%, #14091e 55%, #06030c 100%)",
          }}
          role="status"
          aria-live="polite"
          aria-busy="true"
          aria-label={mode === "call" ? "Звонок завершён, готовим результаты" : "Завершаем тренировку"}
        >
          {/* Top — icon + title + subtitle */}
          <motion.div
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="mb-10 flex flex-col items-center px-8 text-center"
          >
            {/* Phase E (2026-05-08): mode-driven icon. Call mode shows
                a pulsing rose ring with PhoneOff (matches the previous
                CallEndingTransition aesthetic). Chat mode shows a soft
                Sparkles glyph (matches previous SessionEndingOverlay). */}
            {mode === "call" ? (
              <div className="relative mb-5 flex h-20 w-20 items-center justify-center">
                <motion.span
                  className="absolute h-full w-full rounded-full bg-rose-500/15 ring-1 ring-rose-400/30"
                  animate={{ scale: [1, 1.4, 1.4], opacity: [0.6, 0, 0] }}
                  transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
                />
                <motion.div
                  className="relative flex h-14 w-14 items-center justify-center rounded-full bg-rose-500/20 ring-2 ring-rose-300/60"
                  animate={{ scale: [1, 1.04, 1] }}
                  transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                >
                  <PhoneOff className="h-7 w-7 text-rose-100" strokeWidth={2} />
                </motion.div>
              </div>
            ) : (
              <Sparkles
                size={36}
                className="mb-4 text-white/70"
                aria-hidden
              />
            )}
            <h2 className="text-2xl font-semibold tracking-tight">{effectiveTitle}</h2>
            {subtitle && (
              <p className="mt-2 text-sm text-white/60">{subtitle}</p>
            )}
            {/* Call-mode reason text (e.g. "клиент бросил трубку") */}
            {mode === "call" && reason && (
              <p className="mt-3 max-w-sm text-sm text-white/55">{reason}</p>
            )}
          </motion.div>

          {/* Phase list — vertical timeline with check / spinner / dot */}
          <div className="flex w-full max-w-sm flex-col gap-3 px-8">
            {PHASES.slice(0, -1).map((p, i) => {
              const done = i < phaseIdx;
              const active = i === phaseIdx;
              return (
                <motion.div
                  key={p.label}
                  initial={{ x: -12, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  transition={{ delay: 0.15 + i * 0.07 }}
                  className="flex items-center gap-3"
                >
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center">
                    {done ? (
                      <motion.span
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        transition={{ type: "spring", stiffness: 400, damping: 18 }}
                        className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500/90 text-white"
                      >
                        <Check size={14} strokeWidth={3} />
                      </motion.span>
                    ) : active ? (
                      <motion.span
                        animate={{ rotate: 360 }}
                        transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                        className="inline-block h-5 w-5 rounded-full border-2 border-white/25 border-t-white"
                      />
                    ) : (
                      <span className="h-2 w-2 rounded-full bg-white/20" />
                    )}
                  </div>
                  <span
                    className="text-sm transition-colors"
                    style={{
                      color: done
                        ? "rgba(255,255,255,0.55)"
                        : active
                        ? "rgba(255,255,255,0.95)"
                        : "rgba(255,255,255,0.4)",
                      fontWeight: active ? 600 : 400,
                    }}
                  >
                    {p.label}
                  </span>
                </motion.div>
              );
            })}
          </div>

          {/* Call-mode stats chips */}
          {mode === "call" && stats && stats.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4, duration: 0.4 }}
              className="mt-8 flex flex-wrap justify-center gap-2 px-6"
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

          {/* Bottom — flavour text. Phase G: swap to slow-hint after 20s. */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.5 }}
            transition={{ delay: 0.6 }}
            className="mt-12 text-center text-xs text-white/50"
          >
            {showSlowHint ? (
              <span style={{ color: "rgba(255,200,140,0.85)" }}>
                Подсчёт занимает дольше обычного. Подождите ещё немного…
              </span>
            ) : (
              "Это занимает обычно 10–15 секунд"
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
