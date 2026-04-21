"use client";

interface XPBarProps {
  level: number;
  currentXP: number;
  nextLevelXP: number;
  className?: string;
}

export function XPBar({ level, currentXP, nextLevelXP, className = "" }: XPBarProps) {
  const pct = nextLevelXP > 0 ? Math.min((currentXP / nextLevelXP) * 100, 100) : 0;
  // Snap percentage to 10-step increments for pixel stepped feel
  const steppedPct = Math.round(pct / 10) * 10;

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Level badge — pixel font */}
      <div
        className="flex h-6 min-w-[24px] items-center justify-center font-pixel text-base font-bold px-1"
        style={{ background: "var(--accent)", color: "#fff" }}
      >
        {level}
      </div>

      {/* Progress bar — pixel stepped */}
      <div className="flex-1 h-2 overflow-hidden" style={{ background: "var(--input-bg)", border: "1px solid var(--border-color)" }}>
        <div
          className="h-full"
          style={{
            width: `${steppedPct}%`,
            background: "var(--accent)",
            transition: "width 0.3s steps(10)",
          }}
        />
      </div>

      {/* XP counter — pixel font */}
      <span className="font-pixel text-base tabular-nums whitespace-nowrap" style={{ color: "var(--text-muted)" }}>
        {currentXP}/{nextLevelXP}
      </span>
    </div>
  );
}
