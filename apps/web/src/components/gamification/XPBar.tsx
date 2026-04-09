"use client";

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
      {/* Level badge */}
      <div
        className="flex h-6 min-w-[24px] items-center justify-center rounded-md font-mono text-xs font-bold px-1"
        style={{ background: "var(--accent)", color: "#fff" }}
      >
        {level}
      </div>

      {/* Progress bar */}
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: "var(--input-bg)" }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: "var(--accent)" }}
        />
      </div>

      {/* XP counter — inline, not stacked */}
      <span className="font-mono text-xs font-medium tabular-nums whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
        {currentXP}/{nextLevelXP}
      </span>
    </div>
  );
}
