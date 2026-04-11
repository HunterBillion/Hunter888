"use client";

import { useSessionStore } from "@/stores/useSessionStore";

function ScoreBar({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-xs font-medium w-28 truncate" style={{ color: "var(--text-secondary)" }}>
        {label}
      </span>
      <div className="flex-1 h-2 rounded-full" style={{ background: "var(--input-bg)" }}>
        <div
          className="h-full rounded-full transition-all duration-700 ease-out"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="text-xs font-mono w-8 text-right font-bold" style={{ color }}>
        {Math.round(pct)}
      </span>
    </div>
  );
}

export default function RealtimeScores() {
  const scores = useSessionStore((s) => s.realtimeScores);
  const isPrelim = useSessionStore((s) => s.isPreliminaryScore);

  if (!scores) return null;

  return (
    <div className="glass-panel rounded-xl p-4 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-secondary)" }}>
          Скоринг
        </span>
        {isPrelim && (
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full" style={{ background: "rgba(251,191,36,0.15)", color: "#FBB024" }}>
            LIVE
          </span>
        )}
      </div>

      {/* Overall estimate */}
      <div className="flex items-center justify-between">
        <span className="text-base font-bold" style={{ color: "var(--text-primary)" }}>
          {Math.round(scores.realtime_estimate)}/100
        </span>
        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          макс: {Math.round(scores.max_possible_realtime)}
        </span>
      </div>

      <div className="space-y-2">
        <ScoreBar label="Возражения" value={scores.objection_handling} color="var(--danger)" />
        <ScoreBar label="Коммуникация" value={scores.communication} color="var(--accent, #6366f1)" />
        <ScoreBar label="Человечность" value={scores.human_factor} color="var(--success)" />
      </div>
    </div>
  );
}
