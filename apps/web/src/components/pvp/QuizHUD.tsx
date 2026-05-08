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
  const r = 16;
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
      style={{ width: 44, height: 44 }}
    >
      <svg width={44} height={44} className="absolute inset-0">
        <circle cx={22} cy={22} r={r} stroke="var(--border-color)" strokeWidth={3} fill="none" opacity={0.4} />
        <circle
          cx={22}
          cy={22}
          r={r}
          stroke={color}
          strokeWidth={3}
          fill="none"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform="rotate(-90 22 22)"
          style={{
            transition: "stroke-dashoffset 800ms linear, stroke 200ms",
            filter: phase !== "calm" ? `drop-shadow(0 0 4px ${color})` : undefined,
          }}
        />
      </svg>
      <span
        className="font-mono tabular-nums"
        style={{ color, fontSize: 11, fontWeight: 700, letterSpacing: "0.02em" }}
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
        background: "var(--glass-bg, rgba(15,15,20,0.72))",
        backdropFilter: "blur(20px)",
        WebkitBackdropFilter: "blur(20px)",
        borderBottom: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
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
              className="font-display font-bold tracking-widest truncate"
              style={{
                color: accent,
                fontSize: 18,
                textShadow: `0 0 12px ${accent}66`,
                lineHeight: 1.1,
              }}
            >
              ▶ {modeLabel}
            </div>
            {category && (
              <div
                className="font-mono uppercase tracking-wider truncate mt-0.5"
                style={{ color: "var(--text-muted)", fontSize: 11, letterSpacing: "0.12em" }}
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
                style={{ color: "var(--text-primary)", fontSize: 16, letterSpacing: "0.04em" }}
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
                        width: 6,
                        height: 12,
                        background: filled ? accent : "var(--input-bg)",
                        borderRadius: 2,
                        boxShadow: filled ? `0 0 6px ${accent}88` : "none",
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
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg"
              style={{
                background: "rgba(245,158,11,0.1)",
                border: "1px solid rgba(245,158,11,0.3)",
                color: "var(--warning)",
              }}
              title={`Лучшая серия: ${bestStreak}`}
            >
              <Zap size={12} />
              <span className="font-mono font-bold tabular-nums" style={{ fontSize: 12 }}>
                ×{bestStreak}
              </span>
            </motion.div>
          )}
        </div>

        {/* ── RIGHT — score + timer ── */}
        <div className="flex items-center gap-2 ml-auto">
          {(correct > 0 || incorrect > 0) && (
            <div
              className="flex items-center gap-2 px-3 py-1.5 rounded-xl font-mono tabular-nums"
              style={{
                background: "var(--glass-bg, rgba(255,255,255,0.04))",
                border: "1px solid var(--glass-border, rgba(255,255,255,0.08))",
                fontSize: 14,
                fontWeight: 600,
                backdropFilter: "blur(20px)",
              }}
            >
              <span style={{ color: "var(--success)", textShadow: "0 0 6px rgba(34,197,94,0.5)" }}>
                ✓{correct}
              </span>
              <span style={{ color: "var(--text-muted)" }}>·</span>
              <span style={{ color: "var(--danger)", textShadow: "0 0 6px rgba(239,68,68,0.5)" }}>
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
