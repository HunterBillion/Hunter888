"use client";

import { useEffect, useRef } from "react";

interface EmotionEntry {
  state: string;
  timestamp: number;
}

interface EmotionTimelineProps {
  timeline: EmotionEntry[];
}

const STATE_Y: Record<string, number> = {
  cold: 0.8,
  warming: 0.5,
  open: 0.2,
};

const STATE_COLOR: Record<string, string> = {
  cold: "#60A5FA",
  warming: "#FBBF24",
  open: "#00FF66",
};

const STATE_LABEL: Record<string, string> = {
  cold: "Холодный",
  warming: "Теплеет",
  open: "Открыт",
};

export default function EmotionTimeline({ timeline }: EmotionTimelineProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !timeline.length) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = 120;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);

    const padX = 40;
    const padY = 16;
    const plotW = w - padX * 2;
    const plotH = h - padY * 2;

    ctx.clearRect(0, 0, w, h);

    // Grid lines for each state
    Object.entries(STATE_Y).forEach(([state, yPct]) => {
      const y = padY + yPct * plotH;
      ctx.strokeStyle = "rgba(255,255,255,0.05)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padX, y);
      ctx.lineTo(w - padX, y);
      ctx.stroke();

      ctx.fillStyle = "rgba(255,255,255,0.2)";
      ctx.font = "9px 'JetBrains Mono', monospace";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.fillText(STATE_LABEL[state] || state, padX - 6, y);
    });

    // Plot line
    if (timeline.length < 2) return;

    const minT = timeline[0].timestamp;
    const maxT = timeline[timeline.length - 1].timestamp;
    const range = maxT - minT || 1;

    ctx.beginPath();
    for (let i = 0; i < timeline.length; i++) {
      const entry = timeline[i];
      const x = padX + ((entry.timestamp - minT) / range) * plotW;
      const y = padY + (STATE_Y[entry.state] ?? 0.5) * plotH;

      if (i === 0) ctx.moveTo(x, y);
      else {
        // Step function
        const prevEntry = timeline[i - 1];
        const prevX = padX + ((prevEntry.timestamp - minT) / range) * plotW;
        const prevY = padY + (STATE_Y[prevEntry.state] ?? 0.5) * plotH;
        ctx.lineTo(x, prevY);
        ctx.lineTo(x, y);
      }
    }
    ctx.strokeStyle = "#8A2BE2";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Fill under
    const lastX = padX + plotW;
    const lastY = padY + (STATE_Y[timeline[timeline.length - 1].state] ?? 0.5) * plotH;
    ctx.lineTo(lastX, lastY);
    ctx.lineTo(lastX, padY + plotH);
    ctx.lineTo(padX, padY + plotH);
    ctx.closePath();

    const gradient = ctx.createLinearGradient(0, padY, 0, padY + plotH);
    gradient.addColorStop(0, "rgba(138, 43, 226, 0.2)");
    gradient.addColorStop(1, "rgba(138, 43, 226, 0)");
    ctx.fillStyle = gradient;
    ctx.fill();

    // Points with color by state
    for (const entry of timeline) {
      const x = padX + ((entry.timestamp - minT) / range) * plotW;
      const y = padY + (STATE_Y[entry.state] ?? 0.5) * plotH;
      const color = STATE_COLOR[entry.state] || "#8A2BE2";

      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
    }

    // Time axis
    ctx.fillStyle = "rgba(255,255,255,0.15)";
    ctx.font = "9px 'JetBrains Mono', monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText("Начало", padX, padY + plotH + 4);
    ctx.fillText("Конец", w - padX, padY + plotH + 4);
  }, [timeline]);

  if (!timeline.length) return null;

  return (
    <div>
      <canvas
        ref={canvasRef}
        className="w-full"
        style={{ height: 120 }}
      />
      <div className="mt-2 flex justify-center gap-4">
        {Object.entries(STATE_LABEL).map(([key, label]) => (
          <div key={key} className="flex items-center gap-1.5">
            <div
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: STATE_COLOR[key] }}
            />
            <span className="font-mono text-[10px] text-white/30">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
