"use client";

/**
 * QuizHUD — Arcade-Stage HUD bar for the quiz page (Phase 1).
 *
 * Заменяет ad-hoc top-bar в `apps/web/src/app/pvp/quiz/[sessionId]/page.tsx`.
 * Стиль скопирован с /pvp/leaderboard: glass-cards с blur + soft tier-tints,
 * 3-уровневая типографика (font-display headings / font-mono numbers /
 * sans tags), мягкие borders var(--glass-border), tap-feedback scale 0.97.
 *
 * 3 группы:
 *   ◀ Back  ▶ MODE / category sub-line             | LEFT  (mode + back)
 *   Q 7/20  ▓▓▓▓▓░░░░░░░  ⚡×4 streak               | CENTER (progress)
 *   ✓6 ✗1   [⏱ 0:09 dial]                          | RIGHT (score + timer)
 */

import { motion } from "framer-motion";
import { ChevronLeft, Zap } from "lucide-react";
import { categoryLabel } from "@/lib/categories";

interface QuizHUDProps {
  mode: string | null;
  category: string | null;
  currentQuestion: number;
  totalQuestions: number;
  correct: number;
  incorrect: number;
  bestStreak: number;
  timeLeft: number | null;
  onExit: () => void;
}

const MODE_LABEL: Record<string, string> = {
  blitz: "БЛИЦ 20×60",
  rapid_blitz: "RAPID БЛИЦ",
  themed: "ПО ТЕМЕ",
  free_dialog: "ВСЕ ТЕМЫ",
  pvp: "PVP",
};

const MODE_ACCENT: Record<string, string> = {
  blitz: "var(--gf-xp, #facc15)",        // золото — скорость
  rapid_blitz: "var(--warning, #f97316)", // оранж — пожар
  themed: "var(--magenta, #d946ef)",      // мажента — изучение
  free_dialog: "var(--accent)",
  pvp: "var(--accent)",
};

function formatTime(s: number) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

/** Circular timer ring — SVG conic via stroke-dashoffset. */
function TimerDial({ seconds, max = 60 }: { seconds: number; max?: number }) {
  const r = 22;
  const circ = 2 * Math.PI * r;
  const ratio = Math.max(0, Math.min(1, seconds / max));
  const offset = circ * (1 - ratio);
  const phase: "calm" | "warn" | "danger" =
    seconds <= 5 ? "danger" : seconds <= 15 ? "warn" : "calm";
  const color =
    phase === "danger" ? "var(--danger)"
    : phase === "warn" ? "var(--warning)"
    : "var(--success)";
  return (
    <motion.div
      className="relative flex items-center justify-center"
      animate={phase === "danger" ? { scale: [1, 1.06, 1] } : {}}
      transition={{ duration: 0.6, repeat: phase === "danger" ? Infinity : 0 }}
      style={{ width: 56, height: 56 }}
    >
      <svg
        width={56}
        height={56}
        className="absolute inset-0"
        style={{ shapeRendering: "geometricPrecision" }}
      >
        <defs>
          <radialGradient id="dial-bg" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(255,255,255,0.04)" />
            <stop offset="100%" stopColor="rgba(0,0,0,0.18)" />
          </radialGradient>
        </defs>
        <circle cx={28} cy={28} r={r + 3} fill="url(#dial-bg)" />
        <circle cx={28} cy={28} r={r} stroke="var(--border-color)" strokeWidth={3} fill="none" opacity={0.3} />
        <circle
          cx={28}
          cy={28}
          r={r}
          stroke={color}
          strokeWidth={3}
          fill="none"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 28 28)"
          style={{
            transition: "stroke-dashoffset 800ms linear, stroke 200ms",
            filter: phase !== "calm" ? `drop-shadow(0 0 6px ${color})` : `drop-shadow(0 0 2px ${color}88)`,
          }}
        />
      </svg>
      <span
        className="font-display tabular-nums"
        style={{ color, fontSize: 14, fontWeight: 800, letterSpacing: "0.02em", textShadow: `0 0 6px ${color}` }}
      >
        {formatTime(seconds)}
      </span>
    </motion.div>
  );
}

export function QuizHUD({
  mode,
  category,
  currentQuestion,
  totalQuestions,
  correct,
  incorrect,
  bestStreak,
  timeLeft,
  onExit,
}: QuizHUDProps) {
  const modeKey = mode ?? "free_dialog";
  const modeLabel = MODE_LABEL[modeKey] ?? "ДИАЛОГ";
  const accent = MODE_ACCENT[modeKey] ?? "var(--accent)";
  const dotsCount = totalQuestions > 0 ? Math.min(totalQuestions, 20) : 0;

  return (
    <div
      className="shrink-0 sticky top-0 z-20"
      style={{
        background: "linear-gradient(180deg, rgba(15,15,20,0.78) 0%, rgba(15,15,20,0.62) 100%)",
        backdropFilter: "blur(24px) saturate(1.4)",
        WebkitBackdropFilter: "blur(24px) saturate(1.4)",
        borderBottom: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
        boxShadow: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px rgba(0,0,0,0.32)",
      }}
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-3 flex items-center gap-4">
        {/* ── LEFT — back + mode badge ── */}
        <div className="flex items-center gap-3 min-w-0">
          <motion.button
            onClick={onExit}
            whileTap={{ scale: 0.94 }}
            whileHover={{ y: -1 }}
            className="flex items-center justify-center rounded-xl shrink-0"
            style={{
              width: 40,
              height: 40,
              background: "var(--glass-bg, rgba(255,255,255,0.04))",
              border: "1px solid var(--glass-border, rgba(255,255,255,0.1))",
              color: "var(--text-secondary)",
              backdropFilter: "blur(20px)",
              transition: "border-color 160ms",
            }}
            title="Завершить и выйти"
            aria-label="Завершить и выйти"
          >
            <ChevronLeft size={18} />
          </motion.button>
          <div className="min-w-0">
            <div
              className="font-display font-bold tracking-widest truncate uppercase"
              style={{
                color: accent,
                fontSize: 22,
                textShadow: `0 0 16px ${accent}88`,
                lineHeight: 1.1,
                letterSpacing: "0.06em",
              }}
            >
              ▶ {modeLabel}
            </div>
            {category && (
              <div
                className="font-mono uppercase tracking-wider truncate mt-1"
                style={{ color: "var(--text-secondary)", fontSize: 13, letterSpacing: "0.12em" }}
              >
                · {categoryLabel(category)}
              </div>
            )}
          </div>
        </div>

        {/* ── CENTER — progress + counter + streak ── */}
        <div className="flex-1 hidden md:flex items-center justify-center gap-3 min-w-0">
          {totalQuestions > 0 && (
            <>
              <span
                className="font-display font-bold tabular-nums shrink-0"
                style={{ color: "var(--text-primary)", fontSize: 22, letterSpacing: "0.04em", textShadow: `0 0 14px ${accent}55` }}
              >
                Q {currentQuestion}/{totalQuestions}
              </span>
              <div
                className="flex items-center gap-1 px-2 py-1.5 rounded-lg"
                style={{
                  background: "var(--glass-bg, rgba(255,255,255,0.03))",
                  border: "1px solid var(--glass-border, rgba(255,255,255,0.06))",
                }}
                aria-hidden
              >
                {Array.from({ length: dotsCount }).map((_, i) => {
                  const filled = i < Math.round((currentQuestion / totalQuestions) * dotsCount);
                  return (
                    <span
                      key={i}
                      style={{
                        width: 8,
                        height: 16,
                        background: filled ? accent : "var(--input-bg)",
                        borderRadius: 2,
                        boxShadow: filled ? `0 0 8px ${accent}` : "none",
                        transition: "background 220ms, box-shadow 220ms",
                      }}
                    />
                  );
                })}
              </div>
            </>
          )}
          {bestStreak >= 2 && (
            <motion.div
              key={bestStreak}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
              style={{
                background: "rgba(245,158,11,0.14)",
                border: "1px solid rgba(245,158,11,0.4)",
                color: "var(--warning)",
                boxShadow: "0 4px 12px rgba(245,158,11,0.2), inset 0 1px 0 rgba(255,255,255,0.06)",
              }}
              title={`Лучшая серия: ${bestStreak}`}
            >
              <Zap size={16} />
              <span className="font-display font-bold tabular-nums" style={{ fontSize: 16 }}>
                ×{bestStreak}
              </span>
            </motion.div>
          )}
        </div>

        {/* ── RIGHT — score + timer ── */}
        <div className="flex items-center gap-2 ml-auto">
          {(correct > 0 || incorrect > 0) && (
            <div
              className="flex items-center gap-2.5 px-3.5 py-2 rounded-xl font-display font-bold tabular-nums"
              style={{
                background: "var(--glass-bg, rgba(255,255,255,0.04))",
                border: "1px solid var(--glass-border, rgba(255,255,255,0.1))",
                fontSize: 18,
                backdropFilter: "blur(20px)",
                boxShadow: "0 4px 14px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.05)",
              }}
            >
              <span style={{ color: "var(--success)", textShadow: "0 0 8px rgba(34,197,94,0.6)" }}>
                ✓{correct}
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: 14 }}>·</span>
              <span style={{ color: "var(--danger)", textShadow: "0 0 8px rgba(239,68,68,0.6)" }}>
                ✗{incorrect}
              </span>
            </div>
          )}
          {timeLeft !== null && <TimerDial seconds={timeLeft} max={60} />}
        </div>
      </div>
    </div>
  );
}
