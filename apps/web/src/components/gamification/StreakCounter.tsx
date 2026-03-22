"use client";

import { motion } from "framer-motion";
import { Flame } from "lucide-react";

interface StreakCounterProps {
  streak: number;
  className?: string;
}

export function StreakCounter({ streak, className = "" }: StreakCounterProps) {
  const isActive = streak > 0;

  return (
    <motion.div
      className={`flex items-center gap-1.5 rounded-lg px-2 py-1 ${className}`}
      style={{
        background: isActive ? "rgba(255, 153, 0, 0.1)" : "var(--input-bg)",
        border: `1px solid ${isActive ? "rgba(255, 153, 0, 0.2)" : "var(--border-color)"}`,
      }}
      whileHover={{ scale: 1.05 }}
    >
      <motion.div
        animate={isActive ? { scale: [1, 1.2, 1] } : {}}
        transition={{ duration: 0.6, repeat: Infinity, repeatDelay: 2 }}
      >
        <Flame size={14} style={{ color: isActive ? "#ff9900" : "var(--text-muted)" }} />
      </motion.div>
      <span
        className="font-mono text-xs font-bold"
        style={{ color: isActive ? "#ff9900" : "var(--text-muted)" }}
      >
        {streak}
      </span>
    </motion.div>
  );
}
