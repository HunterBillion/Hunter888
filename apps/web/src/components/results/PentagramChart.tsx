"use client";

import { useEffect, useState } from "react";
import {
  Chart as ChartJS,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
} from "chart.js";
import { Radar } from "react-chartjs-2";
import { cssVar } from "@/lib/chartTheme";

ChartJS.register(RadialLinearScale, PointElement, LineElement, Filler, Tooltip);

interface PentagramData {
  labels: string[];
  values: number[];
  previousValues?: number[];
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

export default function PentagramChart({ data }: { data: PentagramData }) {
  const isDark = useIsDark();

  const gridColor = isDark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const labelColor = isDark ? "rgba(255,255,255,0.85)" : "rgba(0,0,0,0.75)";
  const tooltipBg = isDark ? "rgba(5,5,5,0.9)" : "rgba(255,255,255,0.95)";
  const tooltipText = isDark ? "#fff" : "#1a1a1a";
  const pointBorder = isDark ? "#fff" : "#1a1a1a";
  const accentHex = cssVar("--accent", "#7C6AE8");

  // Guard: ensure labels and values arrays are the same length.
  // If mismatched, pad the shorter array to prevent Chart.js rendering artifacts.
  const safeLabels = data.labels;
  const safeValues =
    data.values.length === safeLabels.length
      ? data.values
      : [...data.values, ...Array(Math.max(0, safeLabels.length - data.values.length)).fill(0)].slice(0, safeLabels.length);

  const datasets = [
    {
      label: "Текущая сессия",
      data: safeValues,
      backgroundColor: "rgba(124, 106, 232, 0.3)",
      borderColor: accentHex,
      pointBackgroundColor: accentHex,
      pointBorderColor: pointBorder,
      pointHoverBackgroundColor: pointBorder,
      pointHoverBorderColor: accentHex,
      borderWidth: 2,
    },
  ];

  if (data.previousValues?.length === safeLabels.length) {
    datasets.push({
      label: "Предыдущая сессия",
      data: data.previousValues,
      backgroundColor: "rgba(138, 43, 226, 0.05)",
      borderColor: "rgba(138, 43, 226, 0.25)",
      pointBackgroundColor: "transparent",
      pointBorderColor: "transparent",
      pointHoverBackgroundColor: "transparent",
      pointHoverBorderColor: "transparent",
      borderWidth: 1,
    });
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      r: {
        angleLines: { color: gridColor },
        grid: { color: gridColor },
        pointLabels: {
          font: { family: "'Rajdhani', sans-serif", size: data.labels.length > 6 ? 11 : 13, weight: "bold" as const },
          color: labelColor,
        },
        ticks: { display: false },
        min: 0,
        max: 100,
      },
    },
    plugins: {
      legend: { display: true },
      tooltip: {
        backgroundColor: tooltipBg,
        titleColor: tooltipText,
        bodyColor: tooltipText,
        borderColor: "#8A2BE2",
        borderWidth: 1,
        titleFont: { family: "Rajdhani", size: 14 },
        bodyFont: { family: "Space Grotesk", size: 13 },
      },
    },
  };

  return (
    <div className="relative w-full" style={{ minHeight: 300 }}>
      <Radar data={{ labels: safeLabels, datasets }} options={options} />
    </div>
  );
}
