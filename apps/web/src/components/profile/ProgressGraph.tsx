"use client";

import { useMemo } from "react";
import { motion } from "framer-motion";
import { TrendingUp, BarChart3 } from "lucide-react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Filler,
} from "chart.js";
import { Chart } from "react-chartjs-2";
import { AnimatedChart } from "@/components/ui/AnimatedChart";
import type { ProgressPoint } from "@/types";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Tooltip, Filler);

interface ProgressGraphProps {
  data: ProgressPoint[];
}

export function ProgressGraph({ data }: ProgressGraphProps) {
  const chartData = useMemo(() => {
    if (data.length === 0) return null;

    const labels = data.map((p) => {
      const d = new Date(p.period_start);
      return `${d.getDate().toString().padStart(2, "0")}.${(d.getMonth() + 1).toString().padStart(2, "0")}`;
    });

    return {
      labels,
      datasets: [
        {
          type: "line" as const,
          label: "Средний балл",
          data: data.map((p) => p.avg_total),
          borderColor: "rgba(99,102,241,0.9)",
          backgroundColor: "rgba(99,102,241,0.1)",
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointBackgroundColor: "rgba(99,102,241,1)",
          pointBorderColor: "transparent",
          yAxisID: "y",
          order: 1,
        },
        {
          type: "bar" as const,
          label: "Сессий",
          data: data.map((p) => p.sessions_count),
          backgroundColor: "rgba(99,102,241,0.15)",
          borderRadius: 4,
          yAxisID: "y1",
          order: 2,
        },
      ],
    };
  }, [data]);

  if (!chartData) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-panel p-8 text-center"
      >
        <BarChart3 size={32} className="mx-auto animate-float-subtle" style={{ color: "var(--text-muted)", opacity: 0.4 }} />
        <p className="mt-3 text-sm" style={{ color: "var(--text-muted)" }}>
          Пройдите несколько тренировок для отображения прогресса
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-panel p-6"
    >
      <div className="flex items-center gap-2 mb-4">
        <TrendingUp size={16} style={{ color: "var(--accent)" }} />
        <span className="font-display text-sm font-bold tracking-widest uppercase" style={{ color: "var(--text-secondary)" }}>
          Прогресс
        </span>
      </div>

      <AnimatedChart>
        {(isVisible) => isVisible ? <Chart
          type="bar"
          data={chartData}
          options={{
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 2.5,
            interaction: { mode: "index", intersect: false },
            plugins: {
              tooltip: {
                backgroundColor: "rgba(10,10,22,0.9)",
                borderColor: "rgba(99,102,241,0.3)",
                borderWidth: 1,
                titleFont: { family: "JetBrains Mono", size: 11 },
                bodyFont: { family: "Plus Jakarta Sans", size: 12 },
                padding: 10,
              },
            },
            scales: {
              x: {
                ticks: { color: "rgba(148,148,173,0.6)", font: { family: "JetBrains Mono", size: 10 } },
                grid: { color: "rgba(99,102,241,0.06)" },
              },
              y: {
                position: "left",
                min: 0,
                max: 100,
                ticks: { color: "rgba(148,148,173,0.6)", font: { family: "JetBrains Mono", size: 10 } },
                grid: { color: "rgba(99,102,241,0.06)" },
              },
              y1: {
                position: "right",
                min: 0,
                ticks: { color: "rgba(148,148,173,0.4)", font: { family: "JetBrains Mono", size: 10 } },
                grid: { display: false },
              },
            },
          }}
        /> : null}
      </AnimatedChart>
    </motion.div>
  );
}
