"use client";

import { useSessionStore } from "@/stores/useSessionStore";
import type { EmotionState } from "@/types";

// Map emotions to vertical position (0 = bottom/cold, 100 = top/deal)
const EMOTION_VALUE: Record<string, number> = {
  cold: 5,
  hostile: 10,
  hangup: 10,
  guarded: 20,
  skeptical: 25,
  testing: 35,
  curious: 45,
  considering: 55,
  warming: 60,
  negotiating: 70,
  open: 80,
  callback: 85,
  deal: 95,
};

const EMOTION_COLOR: Record<string, string> = {
  cold: "#93C5FD",
  hostile: "var(--danger)",
  hangup: "var(--danger)",
  guarded: "var(--warning)",
  skeptical: "var(--warning)",
  testing: "#EAB308",
  curious: "#A3E635",
  considering: "#84CC16",
  warming: "var(--success)",
  negotiating: "#14B8A6",
  open: "var(--info)",
  callback: "var(--accent)",
  deal: "var(--success)",
};

export default function LiveEmotionTimeline() {
  const history = useSessionStore((s) => s.emotionHistory);

  if (history.length < 2) return null;

  const W = 200;
  const H = 48;
  const padX = 4;
  const padY = 4;

  const points = history.map((h, i) => {
    const x = padX + (i / (history.length - 1)) * (W - padX * 2);
    const val = EMOTION_VALUE[h.state] ?? 50;
    const y = H - padY - (val / 100) * (H - padY * 2);
    return { x, y, state: h.state };
  });

  const polyline = points.map((p) => `${p.x},${p.y}`).join(" ");
  const lastPoint = points[points.length - 1];
  const lastColor = EMOTION_COLOR[lastPoint.state] || "var(--accent)";

  return (
    <div className="flex flex-col">
      <span className="text-sm font-semibold uppercase tracking-wide" style={{ color: "var(--text-secondary)" }}>
        Динамика эмоций
      </span>
      <svg width={W} height={H} className="w-full mt-1" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {/* Grid lines */}
        <line x1={padX} y1={H / 2} x2={W - padX} y2={H / 2} stroke="var(--border-color, #333)" strokeWidth="0.5" strokeDasharray="2,2" />

        {/* Path */}
        <polyline
          points={polyline}
          fill="none"
          stroke={lastColor}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          opacity="0.8"
        />

        {/* Dots */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={i === points.length - 1 ? 3.5 : 2}
            fill={EMOTION_COLOR[p.state] || "var(--accent)"}
            opacity={i === points.length - 1 ? 1 : 0.6}
          />
        ))}
      </svg>
    </div>
  );
}
