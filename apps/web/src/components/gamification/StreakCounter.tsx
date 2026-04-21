"use client";

import { motion } from "framer-motion";
import { Flame } from "lucide-react";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { STREAK } from "@/lib/constants";

interface StreakCounterProps {
  streak: number;
  className?: string;
}

export function StreakCounter({ streak, className = "" }: StreakCounterProps) {
  const isActive = streak > 0;
  const isMilestone = streak === 7 || streak === 14 || streak === 21 || streak === 30;
  const reducedMotion = useReducedMotion();

  const dayLabel = streak === 1 ? "день" : streak < 5 ? "дня" : "дней";

  // Match PlanChip style — same pill shape, padding, typography — so both
  // header badges look like a visual pair. Typography: text-[11px] semibold
  // uppercase with wide tracking, matching the SCOUT chip next to it.
  const fg = isActive ? STREAK.color : "var(--text-muted)";
  return (
    <motion.div
      className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider whitespace-nowrap shrink-0 ${className}`}
      style={{
        background: isActive ? STREAK.rgba(0.12) : "var(--input-bg)",
        color: fg,
        border: `1px solid ${isActive ? STREAK.rgba(0.4) : "var(--border-color)"}`,
        boxShadow: isMilestone
          ? `0 0 16px ${STREAK.rgba(0.25)}`
          : isActive
            ? `0 0 10px ${STREAK.rgba(0.12)}`
            : "none",
      }}
      whileHover={{ scale: 1.04 }}
      whileTap={{ scale: 0.97 }}
      title={isActive ? `Стрик: ${streak} ${dayLabel} подряд!` : "Начните стрик — тренируйтесь каждый день"}
    >
      <motion.span
        className="inline-flex"
        animate={isActive && !reducedMotion ? { scale: [1, 1.2, 1], rotate: [0, -6, 6, 0] } : {}}
        transition={reducedMotion ? {} : { duration: 0.8, repeat: Infinity, repeatDelay: isMilestone ? 1.0 : 2.5 }}
      >
        <Flame size={12} style={{ color: fg, opacity: isActive ? 1 : 0.5 }} />
      </motion.span>
      {isActive ? (
        <>
          <span className="tabular-nums" style={{ color: STREAK.color }}>{streak}</span>
          <span style={{ color: STREAK.rgba(0.75) }}>{dayLabel}</span>
        </>
      ) : (
        <span>Начни серию</span>
      )}
    </motion.div>
  );
}
