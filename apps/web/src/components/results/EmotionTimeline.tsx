"use client";

import { useEffect, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { type EmotionState, EMOTION_MAP } from "@/types";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip);

interface EmotionEntry {
  state: string;
  timestamp: number;
}

function useIsDark() {
  const [isDark, setIsDark] = useState(true);
  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const obs = new MutationObserver(check);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return isDark;
}

const TICK_LABELS: Record<number, string> = {
  0: "Враждебный",
  5: "Холодный",
  20: "Настороже",
  25: "Проверяет",
  40: "Любопытен",
  45: "Перезвонит",
  60: "Обдумывает",
  75: "Торгуется",
  95: "Сделка",
};

export default function EmotionTimeline({ timeline }: { timeline: EmotionEntry[] }) {
  const isDark = useIsDark();

  if (timeline.length === 0) return null;

  const gridColor = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)";
  const tickColor = isDark ? "rgba(255,255,255,0.5)" : "rgba(0,0,0,0.5)";
  const tooltipBg = isDark ? "rgba(5,5,5,0.9)" : "rgba(255,255,255,0.95)";
  const tooltipText = isDark ? "#fff" : "#1a1a1a";
  const pointBorder = isDark ? "#fff" : "#1a1a1a";

  const labels = timeline.map((e, i) => {
    if (i === 0) return "Начало";
    if (i === timeline.length - 1) return "Конец";
    const m = Math.floor(e.timestamp / 60);
    const s = Math.floor(e.timestamp % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  });

  const dataValues = timeline.map((e) => EMOTION_MAP[e.state as EmotionState]?.value ?? 30);
  const pointColors = timeline.map((e) => EMOTION_MAP[e.state as EmotionState]?.color ?? "#8B5CF6");

  const chartData = {
    labels,
    datasets: [
      {
        label: "Vibe",
        data: dataValues,
        borderColor: "#E028CC",
        backgroundColor: (ctx: { chart: { ctx: CanvasRenderingContext2D } }) => {
          const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 300);
          g.addColorStop(0, "rgba(224, 40, 204, 0.4)");
          g.addColorStop(1, "rgba(139, 92, 246, 0.0)");
          return g;
        },
        borderWidth: 3,
        fill: true,
        tension: 0.4,
        pointBackgroundColor: pointColors,
        pointBorderColor: pointBorder,
        pointBorderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: {
        min: 0,
        max: 100,
        grid: { color: gridColor },
        ticks: {
          font: { family: "JetBrains Mono", size: 10 },
          color: tickColor,
          callback: (value: number | string) => TICK_LABELS[Number(value)] || "",
        },
      },
      x: {
        grid: { display: false },
        ticks: { font: { family: "JetBrains Mono", size: 10 }, color: tickColor },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: tooltipBg,
        titleColor: tooltipText,
        bodyColor: tooltipText,
        borderColor: "#E028CC",
        borderWidth: 1,
        callbacks: {
          label: (ctx: { raw: unknown }) => {
            const val = Number(ctx.raw);
            const label = TICK_LABELS[val] || `${val}%`;
            return label;
          },
        },
      },
    },
  };

  return (
    <div className="relative w-full" style={{ minHeight: 250 }}>
      <Line data={chartData} options={options as never} />
    </div>
  );
}
