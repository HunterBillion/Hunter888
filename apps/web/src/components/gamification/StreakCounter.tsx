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

  return (
    <motion.div
      className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 ${className}`}
      style={{
        background: isActive ? STREAK.rgba(0.1) : "var(--input-bg)",
        border: `1px solid ${isActive ? STREAK.rgba(0.25) : "var(--border-color)"}`,
        boxShadow: isMilestone ? `0 0 16px ${STREAK.rgba(0.2)}` : isActive ? `0 0 12px ${STREAK.rgba(0.08)}` : "none",
      }}
      whileHover={{ scale: 1.06 }}
      whileTap={{ scale: 0.97 }}
      title={isActive ? `Стрик: ${streak} ${dayLabel} подряд!` : "Начните стрик — тренируйтесь каждый день"}
    >
      <motion.div
        animate={isActive && !reducedMotion ? { scale: [1, 1.25, 1], rotate: [0, -8, 8, 0] } : {}}
        transition={reducedMotion ? {} : { duration: 0.8, repeat: Infinity, repeatDelay: isMilestone ? 1.0 : 2.5 }}
      >
        <Flame size={15} style={{ color: isActive ? STREAK.color : "var(--text-muted)", opacity: isActive ? 1 : 0.5 }} />
      </motion.div>
      <span
        className="font-mono text-sm font-black tabular-nums"
        style={{ color: isActive ? STREAK.color : "var(--text-muted)", letterSpacing: "-0.02em" }}
      >
        {isActive ? streak : ""}
      </span>
      <span
        className="font-semibold text-xs uppercase tracking-wide"
        style={{ color: isActive ? STREAK.rgba(0.6) : "var(--text-muted)" }}
      >
        {isActive ? dayLabel : "Начни серию"}
      </span>
    </motion.div>
  );
}
