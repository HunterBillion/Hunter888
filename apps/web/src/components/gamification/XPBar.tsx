"use client";

import { motion } from "framer-motion";
import { Zap } from "lucide-react";

interface XPBarProps {
  level: number;
  currentXP: number;
  nextLevelXP: number;
  className?: string;
}

export function XPBar({ level, currentXP, nextLevelXP, className = "" }: XPBarProps) {
  const pct = nextLevelXP > 0 ? Math.min((currentXP / nextLevelXP) * 100, 100) : 0;

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div
        className="flex h-6 w-6 items-center justify-center rounded-lg font-mono text-[10px] font-bold"
        style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
      >
        {level}
      </div>
      <div className="flex-1">
        <div className="xp-bar h-1.5">
          <motion.div
            className="xp-bar-fill"
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.8, ease: "easeOut" }}
          />
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Zap size={10} style={{ color: "var(--accent)" }} />
        <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
          {currentXP}/{nextLevelXP}
        </span>
      </div>
    </div>
  );
}
