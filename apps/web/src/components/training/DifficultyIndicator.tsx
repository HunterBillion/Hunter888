"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { useSessionStore } from "@/stores/useSessionStore";
import { Twemoji } from "@/components/ui/Twemoji";
import type { DifficultyMode, DifficultyTrend } from "@/stores/useSessionStore";

interface DifficultyIndicatorProps {
  effectiveDifficulty: number;
  modifier: number;
  mode: DifficultyMode;
  trend: DifficultyTrend;
  goodStreak: number;
  badStreak: number;
  hadComeback: boolean;
}

const MODE_CONFIG: Record<DifficultyMode, { emoji: string; label: string; color: string } | null> = {
  normal: null,
  boss: { emoji: "\uD83D\uDC80", label: "Босс", color: "var(--danger)" },
  safe: { emoji: "\uD83D\uDEE1\uFE0F", label: "Безопасный", color: "var(--success, #00FF94)" },
  coaching: { emoji: "\uD83D\uDCDA", label: "Обучение", color: "var(--info)" },
  challenge: { emoji: "\u26A1", label: "Челлендж", color: "var(--warning, #FFD700)" },
  onboarding: { emoji: "\uD83C\uDF31", label: "Старт", color: "var(--success, #00FF94)" },
};

function getDifficultyColor(level: number): string {
  if (level <= 3) return "var(--success, #00FF94)";
  if (level <= 6) return "var(--warning, #FFD700)";
  return "var(--danger)";
}

function getTrendArrow(trend: DifficultyTrend): string {
  if (trend === "rising") return "\u2191";
  if (trend === "falling") return "\u2193";
  return "";
}

export default function DifficultyIndicator({
  effectiveDifficulty,
  modifier,
  mode,
  trend,
  goodStreak,
  badStreak,
  hadComeback,
}: DifficultyIndicatorProps) {
  const [hovered, setHovered] = useState(false);
  const reducedMotion = useReducedMotion();
  const difficultyReason = useSessionStore((s) => s.difficultyReason);
  const prevModeRef = useRef<DifficultyMode>(mode);
  const color = getDifficultyColor(effectiveDifficulty);
  const modeConfig = MODE_CONFIG[mode];
  const trendArrow = getTrendArrow(trend);

  // Track mode changes for sound effect
  useEffect(() => {
    prevModeRef.current = mode;
  }, [mode]);

  const stars = Array.from({ length: 10 }, (_, i) => i < effectiveDifficulty);

  return (
    <div
      className="relative flex flex-col"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Title */}
      <div className="text-sm font-semibold uppercase tracking-wide mb-3" style={{ color: "var(--text-secondary)" }}>
        Сложность
      </div>

      {/* Stars row */}
      <div className="flex items-center gap-[3px] mb-2">
        {stars.map((filled, i) => (
          <motion.span
            key={i}
            initial={false}
            animate={{
              opacity: filled ? 1 : 0.2,
              scale: filled ? 1 : 0.85,
            }}
            transition={reducedMotion ? { duration: 0 } : { duration: 0.4, ease: "easeOut" }}
            className="text-base leading-none"
            style={{ color: filled ? color : "var(--text-muted, #444)" }}
          >
            <Twemoji emoji={"\u2B50"} size={16} />
          </motion.span>
        ))}
        <span className="ml-2 text-sm font-bold tabular-nums" style={{ color }}>
          {effectiveDifficulty}
          {trendArrow && (
            <span className="ml-0.5 text-xs" style={{ color: trend === "rising" ? "var(--danger)" : "var(--success, #00FF94)" }}>
              {trendArrow}
            </span>
          )}
        </span>
      </div>

      {/* Mode badge + Streak */}
      <div className="flex items-center gap-2.5 mt-1.5">
        <AnimatePresence mode="wait">
          {modeConfig && (
            <motion.span
              key={mode}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{
                opacity: 1,
                scale: 1,
                ...(mode === "boss" && !reducedMotion
                  ? { boxShadow: ["0 0 4px rgba(255,42,109,0.4)", "0 0 12px rgba(255,42,109,0.8)", "0 0 4px rgba(255,42,109,0.4)"] }
                  : {}),
              }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={
                mode === "boss" && !reducedMotion
                  ? { boxShadow: { repeat: Infinity, duration: 1.2 }, opacity: { duration: 0.3 }, scale: { duration: 0.3 } }
                  : { duration: 0.3 }
              }
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
              style={{
                background: `color-mix(in srgb, ${modeConfig.color} 13%, transparent)`,
                color: modeConfig.color,
                border: `1px solid color-mix(in srgb, ${modeConfig.color} 27%, transparent)`,
              }}
            >
              <Twemoji emoji={modeConfig.emoji} size={14} /> {modeConfig.label}
            </motion.span>
          )}
        </AnimatePresence>

        {goodStreak >= 3 && (
          <span className="text-sm" title={`Серия: ${goodStreak}`}>
            <Twemoji emoji={"\uD83D\uDD25"} size={14} />{goodStreak}
          </span>
        )}
        {badStreak >= 3 && (
          <span className="text-sm" title={`Ошибки: ${badStreak}`}>
            <Twemoji emoji={"\u2744\uFE0F"} size={14} />{badStreak}
          </span>
        )}
        {hadComeback && (
          <span className="text-sm" title="Камбэк!">
            {"\uD83D\uDD04"}
          </span>
        )}
      </div>

      {/* Tooltip */}
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
            className="absolute left-0 right-0 -bottom-1 translate-y-full z-30 p-3 rounded-lg text-xs leading-relaxed"
            style={{
              background: "var(--surface, #1a1a2e)",
              border: "1px solid var(--glass-border, rgba(255,255,255,0.1))",
              color: "var(--text-secondary, #999)",
              boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            }}
          >
            <p>
              {difficultyReason || "Сложность адаптируется к вашему уровню."}
              <br />
              Модификатор: <span style={{ color: modifier >= 0 ? "var(--success)" : "var(--danger)" }}>
                {modifier >= 0 ? "+" : ""}{modifier}
              </span>
              {trend !== "stable" && (
                <> &middot; Тренд: {trend === "rising" ? "растёт" : "падает"}</>
              )}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
