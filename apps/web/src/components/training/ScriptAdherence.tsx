"use client";

interface ScriptAdherenceProps {
  /** 0–100 percentage */
  progress: number;
  checkpointsHit: number;
  checkpointsTotal: number;
}

export default function ScriptAdherence({
  progress,
  checkpointsHit,
  checkpointsTotal,
}: ScriptAdherenceProps) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-[10px] font-medium uppercase tracking-widest text-white/30">
          Script Adherence
        </span>
        <span className="font-mono text-xs text-vh-purple">
          {checkpointsHit}/{checkpointsTotal}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-gradient-to-r from-vh-purple to-vh-magenta transition-all duration-700"
          style={{ width: `${Math.min(progress, 100)}%` }}
        />
      </div>
      <div className="mt-1 text-right font-mono text-[10px] text-white/30">
        {Math.round(progress)}%
      </div>
    </div>
  );
}
