"use client";

import { useEffect, useRef } from "react";

interface PentagramData {
  labels: string[];
  values: number[]; // 0-100 each
}

interface PentagramChartProps {
  data: PentagramData;
  size?: number;
}

export default function PentagramChart({ data, size = 280 }: PentagramChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const maxR = size * 0.38;
    const n = data.labels.length;
    const angleStep = (Math.PI * 2) / n;
    const startAngle = -Math.PI / 2;

    ctx.clearRect(0, 0, size, size);

    // Grid rings
    for (let ring = 1; ring <= 4; ring++) {
      const r = (ring / 4) * maxR;
      ctx.beginPath();
      for (let i = 0; i <= n; i++) {
        const angle = startAngle + i * angleStep;
        const x = cx + r * Math.cos(angle);
        const y = cy + r * Math.sin(angle);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.strokeStyle = "rgba(255,255,255,0.06)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Axis lines
    for (let i = 0; i < n; i++) {
      const angle = startAngle + i * angleStep;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + maxR * Math.cos(angle), cy + maxR * Math.sin(angle));
      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Data polygon fill
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const angle = startAngle + i * angleStep;
      const r = (data.values[i] / 100) * maxR;
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();

    const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR);
    gradient.addColorStop(0, "rgba(138, 43, 226, 0.3)");
    gradient.addColorStop(1, "rgba(138, 43, 226, 0.05)");
    ctx.fillStyle = gradient;
    ctx.fill();

    // Data polygon stroke
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const angle = startAngle + i * angleStep;
      const r = (data.values[i] / 100) * maxR;
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = "#8A2BE2";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Data points
    for (let i = 0; i < n; i++) {
      const angle = startAngle + i * angleStep;
      const r = (data.values[i] / 100) * maxR;
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);

      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#8A2BE2";
      ctx.fill();
      ctx.strokeStyle = "rgba(138, 43, 226, 0.5)";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // Labels
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "10px 'JetBrains Mono', monospace";

    for (let i = 0; i < n; i++) {
      const angle = startAngle + i * angleStep;
      const labelR = maxR + 24;
      const x = cx + labelR * Math.cos(angle);
      const y = cy + labelR * Math.sin(angle);

      ctx.fillStyle = "rgba(255,255,255,0.4)";
      ctx.fillText(data.labels[i], x, y - 6);
      ctx.fillStyle = "rgba(138, 43, 226, 0.8)";
      ctx.font = "bold 11px 'JetBrains Mono', monospace";
      ctx.fillText(`${Math.round(data.values[i])}`, x, y + 8);
      ctx.font = "10px 'JetBrains Mono', monospace";
    }
  }, [data, size]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: size, height: size }}
      className="mx-auto"
    />
  );
}
