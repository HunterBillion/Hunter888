"use client";

/**
 * SessionEndingOverlay (2026-04-23)
 *
 * Full-screen overlay shown between «Завершить» click and arrival on
 * /results page. Replaces the old «session.ended → setTimeout(500ms)»
 * dead air where users saw an unresponsive chat panel for up to 15
 * seconds while backend ran scoring + AI-coach + RAG enrichment.
 *
 * Visual: brand-purple radial gradient, animated phases timeline,
 * spinner + estimated remaining time. Phases match the backend's
 * actual session-end pipeline so the messaging feels honest:
 *   1. Saving conversation       (~50ms)  — db.commit
 *   2. Scoring 5 layers          (~3-8s)  — calculate_scores
 *   3. AI coach analysis         (~5-12s) — narrative + legal layers
 *   4. Achievements / XP         (~1s)    — awards + level-up
 *   5. Готово                    — redirect happens
 *
 * Each phase auto-advances on a timer (ESTIMATES below). When parent
 * receives session.ended event from backend, it just unmounts this
 * component (router.replace to /results). If a phase is over-estimated,
 * the spinner stays on the last shown phase rather than skipping.
 */

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Check, Sparkles } from "lucide-react";

const PHASES: { label: string; etaMs: number }[] = [
  { label: "Сохраняем разговор", etaMs: 600 },
  { label: "Считаем баллы", etaMs: 4500 },
  { label: "Готовим разбор от AI-коуча", etaMs: 7000 },
  { label: "Начисляем достижения и XP", etaMs: 1200 },
  { label: "Готово", etaMs: 0 },
];

export interface SessionEndingOverlayProps {
  /** Title shown at the top of the overlay (e.g. "Звонок завершён"). */
  title?: string;
  /** Subtitle (e.g. character name). */
  subtitle?: string;
  /** Visible from the moment user clicks «Завершить». */
  visible: boolean;
}

export default function SessionEndingOverlay({
  title = "Завершаем тренировку",
  subtitle,
  visible,
}: SessionEndingOverlayProps) {
  const [phaseIdx, setPhaseIdx] = useState(0);

  useEffect(() => {
    if (!visible) {
      setPhaseIdx(0);
      return;
    }
    if (phaseIdx >= PHASES.length - 1) return;
    const eta = PHASES[phaseIdx].etaMs;
    const t = window.setTimeout(() => setPhaseIdx((i) => Math.min(i + 1, PHASES.length - 1)), eta);
    return () => window.clearTimeout(t);
  }, [visible, phaseIdx]);

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
        >
          {/* Top — title + subtitle */}
          <motion.div
            initial={{ y: -20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="mb-12 px-8 text-center"
          >
            <Sparkles
              size={36}
              className="mx-auto mb-4 text-white/70"
              aria-hidden
            />
            <h2 className="text-2xl font-semibold tracking-tight">{title}</h2>
            {subtitle && (
              <p className="mt-2 text-sm text-white/60">{subtitle}</p>
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

          {/* Bottom — flavour text */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.5 }}
            transition={{ delay: 0.6 }}
            className="mt-12 text-xs text-white/50"
          >
            Это занимает обычно 10–15 секунд
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
