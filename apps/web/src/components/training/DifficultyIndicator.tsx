"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { useSessionStore } from "@/stores/useSessionStore";
import { AppIcon } from "@/components/ui/AppIcon";
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

const MODE_CONFIG: Record<DifficultyMode, { emoji: string; label: string; color: string; pixelIcon: string } | null> = {
  normal: null,
  boss: { emoji: "💀", label: "БОСС", color: "var(--danger)", pixelIcon: "💀" },
  safe: { emoji: "🛡️", label: "ЗАЩИТА", color: "var(--success)", pixelIcon: "🛡️" },
  coaching: { emoji: "📚", label: "ОБУЧЕНИЕ", color: "var(--info)", pixelIcon: "📚" },
  challenge: { emoji: "⚡", label: "ЧЕЛЛЕНДЖ", color: "var(--warning)", pixelIcon: "⚡" },
  onboarding: { emoji: "🌱", label: "СТАРТ", color: "var(--success)", pixelIcon: "🌱" },
};

// Game-style difficulty levels
const DIFFICULTY_LEVELS = [
  { max: 3, label: "EASY", color: "#28c840", icon: "🛡️" },
  { max: 5, label: "NORMAL", color: "#d4a84b", icon: "⚔️" },
  { max: 7, label: "HARD", color: "#ff8800", icon: "💀" },
  { max: 10, label: "NIGHTMARE", color: "#ff5f57", icon: "🐉" },
];

function getDifficultyLevel(d: number) {
  return DIFFICULTY_LEVELS.find((l) => d <= l.max) ?? DIFFICULTY_LEVELS[3];
}

function getTrendArrow(trend: DifficultyTrend): string {
  if (trend === "rising") return "↑";
  if (trend === "falling") return "↓";
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
  const level = getDifficultyLevel(effectiveDifficulty);
  const modeConfig = MODE_CONFIG[mode];
  const trendArrow = getTrendArrow(trend);

  useEffect(() => {
    prevModeRef.current = mode;
  }, [mode]);

  return (
    <div
      className="relative flex flex-col"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Pixel title */}
      <div className="font-pixel text-xs uppercase tracking-wider mb-3" style={{ color: "var(--text-muted)" }}>
        СЛОЖНОСТЬ
      </div>

      {/* Game difficulty bar */}
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{level.icon}</span>
        <div className="flex-1">
          {/* Pixel-style progress bar */}
          <div className="h-3 rounded-none pixel-border flex overflow-hidden" style={{ "--pixel-border-color": level.color } as React.CSSProperties}>
            {Array.from({ length: 10 }, (_, i) => (
              <motion.div
                key={i}
                className="flex-1 h-full"
                initial={false}
                animate={{
                  // FIX: motion can't animate from color to "transparent" keyword.
                  // Use rgba(0,0,0,0) — same visual, but motion interpolates it as a color.
                  backgroundColor: i < effectiveDifficulty ? level.color : "rgba(0,0,0,0)",
                  opacity: i < effectiveDifficulty ? 1 : 0.15,
                }}
                transition={reducedMotion ? { duration: 0 } : { duration: 0.3, delay: i * 0.03 }}
                style={{ borderRight: i < 9 ? "1px solid rgba(0,0,0,0.3)" : "none" }}
              />
            ))}
          </div>
        </div>
        <span className="font-pixel text-sm font-bold tabular-nums min-w-[2.5rem] text-right" style={{ color: level.color }}>
          {effectiveDifficulty}/10
          {trendArrow && (
            <span className="ml-0.5 text-xs" style={{ color: trend === "rising" ? "var(--danger)" : "var(--success)" }}>
              {trendArrow}
            </span>
          )}
        </span>
      </div>

      {/* Difficulty label */}
      <div className="font-pixel text-xs uppercase tracking-wider pixel-glow mb-2" style={{ color: level.color }}>
        {level.label}
      </div>

      {/* Mode badge + Streak */}
      <div className="flex items-center gap-2.5">
        <AnimatePresence mode="wait">
          {modeConfig && (
            <motion.span
              key={mode}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{
                opacity: 1,
                scale: 1,
                ...(mode === "boss" && !reducedMotion
                  ? { boxShadow: ["0 0 4px rgba(229,72,77,0.4)", "0 0 12px rgba(229,72,77,0.8)", "0 0 4px rgba(229,72,77,0.4)"] }
                  : {}),
              }}
              exit={{ opacity: 0, scale: 0.8 }}
              transition={
                mode === "boss" && !reducedMotion
                  ? { boxShadow: { repeat: Infinity, duration: 1.2 }, opacity: { duration: 0.3 }, scale: { duration: 0.3 } }
                  : { duration: 0.3 }
              }
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-none text-xs font-pixel uppercase tracking-wider pixel-border"
              style={{
                "--pixel-border-color": modeConfig.color,
                background: `color-mix(in srgb, ${modeConfig.color} 13%, transparent)`,
                color: modeConfig.color,
              } as React.CSSProperties}
            >
              <AppIcon emoji={modeConfig.pixelIcon} size={14} /> {modeConfig.label}
            </motion.span>
          )}
        </AnimatePresence>

        {goodStreak >= 3 && (
          <span className="font-pixel text-xs" title={`Серия: ${goodStreak}`} style={{ color: "var(--warning)" }}>
            🔥{goodStreak}
          </span>
        )}
        {badStreak >= 3 && (
          <span className="font-pixel text-xs" title={`Ошибки: ${badStreak}`} style={{ color: "var(--info)" }}>
            ❄️{badStreak}
          </span>
        )}
        {hadComeback && (
          <span className="font-pixel text-xs" title="Камбэк!" style={{ color: "var(--success)" }}>
            🔄
          </span>
        )}
      </div>

      {/* Pixel tooltip */}
      <AnimatePresence>
        {hovered && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
            className="absolute left-0 right-0 -bottom-1 translate-y-full z-30 p-3 rounded-none text-xs leading-relaxed font-pixel pixel-border pixel-shadow"
            style={{
              "--pixel-border-color": "var(--accent)",
              background: "#0e0b1a",
              color: "var(--text-secondary)",
            } as React.CSSProperties}
          >
            <p>
              {difficultyReason || "Сложность адаптируется к вашему уровню."}
              <br />
              <span style={{ color: "var(--text-muted)" }}>MOD: </span>
              <span style={{ color: modifier >= 0 ? "var(--success)" : "var(--danger)" }}>
                {modifier >= 0 ? "+" : ""}{modifier}
              </span>
              {trend !== "stable" && (
                <> · ТРЕНД: {trend === "rising" ? "↑ растёт" : "↓ падает"}</>
              )}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
