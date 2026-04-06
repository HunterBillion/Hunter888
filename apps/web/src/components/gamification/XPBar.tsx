"use client";

import { motion } from "framer-motion";
import { Zap } from "lucide-react";

interface XPBarProps {
  level: number;
  currentXP: number;
  nextLevelXP: number;
  className?: string;
}

const SEGMENTS = 12;

export function XPBar({ level, currentXP, nextLevelXP, className = "" }: XPBarProps) {
  const pct = nextLevelXP > 0 ? Math.min((currentXP / nextLevelXP) * 100, 100) : 0;
  const filledSegments = Math.round((pct / 100) * SEGMENTS);

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Level badge — mono terminal style */}
      <div
        className="flex h-7 w-7 items-center justify-center rounded-md font-mono text-xs font-black"
        style={{
          background: "var(--accent)",
          color: "#fff",
          boxShadow: "0 0 12px var(--accent-glow)",
          letterSpacing: "-0.02em",
        }}
      >
        {level}
      </div>

      {/* Segmented XP bar — terminal blocks */}
      <div className="flex flex-1 items-center gap-[2px]">
        {Array.from({ length: SEGMENTS }, (_, i) => {
          const isFilled = i < filledSegments;
          return (
            <motion.div
              key={i}
              className="h-2 flex-1 rounded-[2px]"
              initial={{ opacity: 0, scaleY: 0.3 }}
              animate={{
                opacity: isFilled ? 1 : 0.15,
                scaleY: 1,
                background: isFilled
                  ? "var(--accent)"
                  : "var(--input-bg)",
              }}
              transition={{ duration: 0.3, delay: i * 0.04 }}
              style={{
                boxShadow: isFilled ? "0 0 6px var(--accent-glow)" : "none",
              }}
            />
          );
        })}
      </div>

      {/* XP counter — mono data */}
      <div className="flex items-center gap-1">
        <Zap size={12} style={{ color: "var(--accent)" }} />
        <span className="font-mono text-xs font-bold tabular-nums" style={{ color: "var(--text-muted)" }}>
          {currentXP}<span style={{ opacity: 0.4 }}>/</span>{nextLevelXP}
        </span>
      </div>
    </div>
  );
}
