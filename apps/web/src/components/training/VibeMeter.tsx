"use client";

import type { EmotionState } from "@/types";

interface VibeMeterProps {
  emotion: EmotionState;
}

const LEVELS: { state: EmotionState; label: string; color: string }[] = [
  { state: "cold", label: "COLD", color: "bg-blue-400" },
  { state: "warming", label: "WARM", color: "bg-yellow-400" },
  { state: "open", label: "DEAL", color: "bg-vh-green" },
];

export default function VibeMeter({ emotion }: VibeMeterProps) {
  const activeIndex = LEVELS.findIndex((l) => l.state === emotion);

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-3">
      <div className="mb-2 font-mono text-[10px] font-medium uppercase tracking-widest text-white/30">
        Vibe Meter
      </div>
      <div className="flex items-center gap-1">
        {LEVELS.map((level, i) => (
          <div key={level.state} className="flex-1">
            <div
              className={`h-2 rounded-full transition-all duration-500 ${
                i <= activeIndex
                  ? `${level.color} shadow-sm`
                  : "bg-white/10"
              }`}
            />
            <div
              className={`mt-1 text-center font-mono text-[9px] transition-colors duration-300 ${
                i === activeIndex ? "text-white/70" : "text-white/20"
              }`}
            >
              {level.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
